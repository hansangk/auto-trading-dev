from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .config import ExecutionConfig, RiskConfig
from .data import BTC_ETFS, MarketData
from .strategy import StrategySpec


@dataclass(frozen=True)
class BacktestResult:
    total_return: float
    max_drawdown: float
    sharpe: float
    sortino: float
    calmar: float
    win_rate: float
    profit_factor: float
    trades: int
    rounds: int
    turnover: float
    costs: float
    long_pnl: float
    short_pnl: float
    bitcoin_etf_pnl: float
    hard_halts: int
    mdd_halt: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _daily_metrics(round_returns: np.ndarray, round_times: np.ndarray) -> tuple[float, float]:
    if len(round_returns) == 0:
        return 0.0, 0.0
    dates = pd.to_datetime(round_times, utc=True).date
    daily = pd.Series(round_returns).groupby(dates).apply(lambda x: float(np.prod(1 + x) - 1)).to_numpy()
    if len(daily) < 2 or np.std(daily, ddof=1) == 0:
        return 0.0, 0.0
    sharpe = np.sqrt(252) * np.mean(daily) / np.std(daily, ddof=1)
    downside = daily[daily < 0]
    sortino = 0.0 if len(downside) < 2 or np.std(downside, ddof=1) == 0 else np.sqrt(252) * np.mean(daily) / np.std(downside, ddof=1)
    return float(sharpe), float(sortino)


def run_backtest(
    data: MarketData,
    score: np.ndarray,
    spec: StrategySpec,
    execution: ExecutionConfig,
    risk: RiskConfig,
    capital: float,
    start: int = 0,
    stop: int | None = None,
    cost_multiplier: float = 1.0,
    signal_delay_bars: int = 0,
    regime_plan: tuple[np.ndarray, dict[int, tuple[StrategySpec, np.ndarray]]] | None = None,
    short_exclude_symbols: frozenset[str] = frozenset(),
    trade_log: list[dict] | None = None,
    exit_mode: str = 'independent',
    early_reentry: bool = False,
    asset_weight_scale: np.ndarray | None = None,
) -> BacktestResult:
    if asset_weight_scale is not None:
        if asset_weight_scale.shape != data.shape or not np.isfinite(asset_weight_scale).all() or np.any(asset_weight_scale <= 0) or np.any(asset_weight_scale > 1):
            raise ValueError('Asset scales must match data and be finite in (0,1]')
        if spec.long_k != 1 or spec.short_k != 1 or regime_plan is not None:
            raise ValueError('Asset scaling currently supports fixed one-long/one-short specs')
    if exit_mode not in {'independent', 'joint_close', 'fixed_close'}:
        raise ValueError('Unsupported exit mode')
    stop = len(data.timestamps) if stop is None else stop
    i = max(start, 1 + signal_delay_bars)
    equity = float(capital); peak = equity; daily_start = equity
    current_date = None; cooldown_until = -1; loss_streak = 0; hard_halts = 0; killed = False
    returns: list[float] = []; times: list[np.datetime64] = []
    long_pnl = short_pnl = btc_pnl = costs_paid = turnover = 0.0
    stop_fraction = spec.stop_loss_bps / 10_000
    leg_cap = min(risk.max_asset_weight, risk.risk_per_trade / max(stop_fraction, 1e-9))
    side_gross = min(risk.gross_exposure / 2, spec.long_k * leg_cap, spec.short_k * leg_cap)
    per_long = side_gross / spec.long_k; per_short = side_gross / spec.short_k; gross = side_gross * 2
    roundtrip_bps = 2 * (execution.commission_bps + execution.slippage_bps) * cost_multiplier
    borrow_per_bar = execution.short_borrow_bps_per_year / 10_000 * data.bar_minutes / (252 * 390)
    btc_indices = {j for j, symbol in enumerate(data.symbols) if symbol in BTC_ETFS}
    dates = pd.to_datetime(data.timestamps, utc=True).date

    while i < stop:
        date = dates[i]
        if date != current_date:
            current_date = date; daily_start = equity; cooldown_until = min(cooldown_until, i)
        if killed:
            break
        daily_return = equity / daily_start - 1
        if daily_return <= -risk.daily_hard_loss:
            hard_halts += 1
            while i < stop and dates[i] == current_date:
                i += 1
            continue
        if daily_return <= -risk.daily_soft_loss or i < cooldown_until:
            i += 1; continue
        if regime_plan is not None:
            regimes, strategies = regime_plan
            selection = strategies.get(int(regimes[i - 1 - signal_delay_bars]))
            if selection is None:
                i += 1
                continue
            spec, score = selection
            stop_fraction = spec.stop_loss_bps / 10_000
            leg_cap = min(risk.max_asset_weight, risk.risk_per_trade / max(stop_fraction, 1e-9))
            side_gross = min(risk.gross_exposure / 2, spec.long_k * leg_cap, spec.short_k * leg_cap)
            per_long = side_gross / spec.long_k; per_short = side_gross / spec.short_k; gross = side_gross * 2
        signal = score[i - 1 - signal_delay_bars]
        if not np.any(signal) or np.allclose(signal, signal[0]):
            i += 1; continue
        order = np.argsort(signal)
        long_idx = order[-spec.long_k:]
        short_idx = np.array([j for j in order if data.symbols[j] not in short_exclude_symbols and j not in long_idx][:spec.short_k], dtype=int)
        if len(short_idx) != spec.short_k:
            i += 1; continue
        # At the open of bar i, its eventual volume is not yet known.
        if set(short_idx).intersection(long_idx) or np.any(data.volume[i - 1, np.r_[short_idx, long_idx]] <= 0):
            i += 1; continue
        end = min(stop - 1, i + spec.hold_bars - 1)
        while end > i and dates[end] != date:
            end -= 1
        entry = data.open[i]
        if asset_weight_scale is not None:
            # Completed signal-time scales only; reduce, never enlarge, a leg.
            scales = asset_weight_scale[i - 1 - signal_delay_bars]
            per_long = side_gross * float(scales[long_idx[0]])
            per_short = side_gross * float(scales[short_idx[0]])
            gross = per_long + per_short
        scheduled_end = end
        tp_fraction = stop_fraction * spec.take_profit_multiple
        long_returns: list[tuple[int, float]] = []
        short_returns: list[tuple[int, float]] = []
        for idx in long_idx:
            result = data.close[end, idx] / entry[idx] - 1
            for j in range(i, end + 1):
                if data.low[j, idx] <= entry[idx] * (1 - stop_fraction):
                    gap = data.open[j, idx] / entry[idx] - 1
                    result = min(gap, -stop_fraction); break
                if data.high[j, idx] >= entry[idx] * (1 + tp_fraction):
                    result = tp_fraction; break
            long_returns.append((int(idx), float(result)))
        for idx in short_idx:
            result = -(data.close[end, idx] / entry[idx] - 1)
            for j in range(i, end + 1):
                if data.high[j, idx] >= entry[idx] * (1 + stop_fraction):
                    gap = -(data.open[j, idx] / entry[idx] - 1)
                    result = min(gap, -stop_fraction); break
                if data.low[j, idx] <= entry[idx] * (1 - tp_fraction):
                    result = tp_fraction; break
            short_returns.append((int(idx), float(result)))
        if exit_mode != 'independent':
            exit_prices = data.close[end]
            if exit_mode == 'joint_close':
                for j in range(i, end):
                    pair_move = (per_long * np.sum(data.close[j, long_idx] / entry[long_idx] - 1)
                                 - per_short * np.sum(data.close[j, short_idx] / entry[short_idx] - 1)) / gross
                    if pair_move <= -stop_fraction or pair_move >= tp_fraction:
                        end = j + 1
                        exit_prices = data.open[end]
                        break
            long_returns = [(int(k), float(exit_prices[k]/entry[k]-1)) for k in long_idx]
            short_returns = [(int(k), float(1-exit_prices[k]/entry[k])) for k in short_idx]
        long_contribution = per_long * sum(value for _, value in long_returns)
        short_contribution = per_short * sum(value for _, value in short_returns)
        cost_return = gross * roundtrip_bps / 10_000 + per_short * spec.short_k * borrow_per_bar * (end - i + 1)
        round_return = long_contribution + short_contribution - cost_return
        base = equity; equity *= 1 + round_return
        long_pnl += base * long_contribution; short_pnl += base * short_contribution
        btc_pnl += base * (
            per_long * sum(value for idx, value in long_returns if idx in btc_indices)
            + per_short * sum(value for idx, value in short_returns if idx in btc_indices)
        )
        costs_paid += base * cost_return; turnover += gross * 2
        returns.append(round_return); times.append(data.timestamps[end])
        if trade_log is not None:
            trade_log.append(dict(entry=str(data.timestamps[i]), end=str(data.timestamps[end]),
                                  strategy_id=spec.strategy_id, long_symbols=[data.symbols[j] for j in long_idx],
                                  short_symbols=[data.symbols[j] for j in short_idx],
                                  gross_return=long_contribution+short_contribution,
                                  cost_return=cost_return, net_return=round_return,
                                  pnl=base*round_return, equity=equity,
                                  signal_index=i-1-signal_delay_bars))
            trade_log[-1].update(long_weight=per_long,short_weight=per_short,
                                 long_gross_return=long_contribution,
                                 short_gross_return=short_contribution)
        if round_return < 0:
            loss_streak += 1
            if loss_streak >= risk.max_loss_streak:
                cooldown_until = end + spec.cooldown_bars; loss_streak = 0
        else:
            loss_streak = 0
        peak = max(peak, equity)
        if equity / peak - 1 <= -risk.max_drawdown:
            killed = True
        i = (end if early_reentry and end < scheduled_end else scheduled_end) + 1

    arr = np.asarray(returns, dtype=float); time_arr = np.asarray(times)
    max_drawdown = 0.0
    if len(arr):
        curve = np.r_[capital, capital * np.cumprod(1 + arr)]; peaks = np.maximum.accumulate(curve)
        max_drawdown = abs(float(np.min(curve / peaks - 1)))
    sharpe, sortino = _daily_metrics(arr, time_arr)
    wins = arr[arr > 0]; losses = arr[arr < 0]
    profit_factor = float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() else (float("inf") if len(wins) else 0.0)
    total_return = equity / capital - 1
    calmar = total_return / max_drawdown if max_drawdown > 0 else 0.0
    return BacktestResult(
        total_return, max_drawdown, sharpe, sortino, calmar,
        float(np.mean(arr > 0)) if len(arr) else 0.0, profit_factor,
        len(arr) * (spec.long_k + spec.short_k), len(arr), turnover, costs_paid,
        long_pnl, short_pnl, btc_pnl, hard_halts, killed,
    )
