from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .data import MarketData


@dataclass
class FeatureCache:
    data: MarketData

    def __post_init__(self) -> None:
        self._cache: dict[str, np.ndarray] = {}
        self._rank_cache: dict[str, np.ndarray] = {}

    def get(self, name: str) -> np.ndarray:
        if name not in self._cache:
            values = self._compute(name)
            self._cache[name] = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
        return self._cache[name]

    def cross_sectional_rank(self, name: str) -> np.ndarray:
        """Return centered percentile ranks; ties receive the same score.

        Centering is essential during indicator warm-up: an all-zero row must
        produce no preference instead of a deterministic symbol-order trade.
        """
        if name not in self._rank_cache:
            feature = pd.DataFrame(self.get(name))
            ranked = feature.rank(axis=1, method="average", pct=True).to_numpy(dtype=np.float32)
            ranked -= ranked.mean(axis=1, keepdims=True)
            scale = np.max(np.abs(ranked), axis=1, keepdims=True)
            ranked = np.divide(ranked, scale, out=np.zeros_like(ranked), where=scale > 0)
            self._rank_cache[name] = ranked
        return self._rank_cache[name]

    @staticmethod
    def _frame(values: np.ndarray) -> pd.DataFrame:
        return pd.DataFrame(values)

    def _z(self, values: np.ndarray, window: int) -> np.ndarray:
        frame = self._frame(values)
        mean = frame.rolling(window, min_periods=window).mean()
        std = frame.rolling(window, min_periods=window).std(ddof=0).replace(0, np.nan)
        return ((frame - mean) / std).to_numpy()

    def _atr(self, window: int) -> np.ndarray:
        prev = np.vstack([self.data.close[0], self.data.close[:-1]])
        tr = np.maximum(
            self.data.high - self.data.low,
            np.maximum(np.abs(self.data.high - prev), np.abs(self.data.low - prev)),
        )
        return self._frame(tr).rolling(window, min_periods=window).mean().to_numpy()

    def _compute(self, name: str) -> np.ndarray:
        c, h, l, v = self.data.close, self.data.high, self.data.low, self.data.volume
        if name.startswith("stoch_") or name.startswith("williams_"):
            w = int(name.split("_")[1]); hi = self._frame(h).rolling(w).max(); lo = self._frame(l).rolling(w).min()
            k = (self._frame(c) - lo) / (hi - lo).replace(0, np.nan)
            return (k - .5).to_numpy() if name.startswith("stoch_") else (.5 - k).to_numpy()
        if name.startswith("macd_") and not name.startswith("macd_volume_"):
            fast, slow, sig = map(int, name.split("_")[1:]); line = self._frame(c).ewm(span=fast,adjust=False).mean()-self._frame(c).ewm(span=slow,adjust=False).mean()
            return ((line-line.ewm(span=sig,adjust=False).mean())/self._frame(c)).to_numpy()
        if name.startswith("cci_"):
            w=int(name.split("_")[1]);tp=self._frame((h+l+c)/3); avg=tp.rolling(w).mean();dev=(tp-avg).abs().rolling(w).mean()
            return ((tp-avg)/(0.015*dev.replace(0,np.nan))).to_numpy()
        if name.startswith("mfi_"):
            w=int(name.split("_")[1]);typ=self._frame((h+l+c)/3);flow=typ*self._frame(v);delta=typ.diff();plus=flow.where(delta>0,0).rolling(w).sum();minus=flow.where(delta<0,0).rolling(w).sum()
            return ((plus-minus)/(plus+minus).replace(0,np.nan)).to_numpy()
        if name.startswith("bbwidth_"):
            w=int(name.split("_")[1]); f=self._frame(c);return (4*f.rolling(w).std()/f.rolling(w).mean()).to_numpy()
        if name.startswith("keltner_"):
            w=int(name.split("_")[1]); mid=self._frame(c).ewm(span=w,adjust=False).mean();return ((self._frame(c)-mid)/self._frame(self._atr(w)).replace(0,np.nan)).to_numpy()
        if name.startswith("stochrsi_"):
            w=int(name.split("_")[1]);delta=self._frame(c).diff();up=delta.clip(lower=0).rolling(w).mean();down=(-delta.clip(upper=0)).rolling(w).mean();rsi=100-100/(1+up/down.replace(0,np.nan));lo=rsi.rolling(w).min();hi=rsi.rolling(w).max()
            return (-((rsi-lo)/(hi-lo).replace(0,np.nan)-.5)).to_numpy()
        if name.startswith("bb_rsi_"):
            w=int(name.split("_")[2]);return .5*(-self._z(c,w))+.5*self._compute('rsi_'+str(w))
        if name.startswith("macd_volume_"):
            w=int(name.split("_")[2]);return self._compute('macd_5_20_7')*(1+np.clip(self._z(np.log1p(v),w),-2,2)*.2)
        if name.startswith("ema_"):
            fast, slow = map(int, name.split("_")[1:])
            ef = self._frame(c).ewm(span=fast, adjust=False).mean()
            es = self._frame(c).ewm(span=slow, adjust=False).mean()
            return (ef / es - 1).to_numpy()
        if name.startswith("roc_"):
            return self._frame(c).pct_change(int(name.split("_")[1])).to_numpy()
        if name.startswith("momentum_"):
            w = int(name.split("_")[1])
            return (self._frame(c).pct_change(w) + .5 * self._frame(c).pct_change(max(1, w // 3))).to_numpy()
        if name.startswith("slope_"):
            w = int(name.split("_")[1])
            return self._frame(np.log(c)).diff(w).to_numpy() / w
        if name.startswith("zclose_"):
            return -self._z(c, int(name.split("_")[1]))
        if name.startswith("rsi_"):
            w = int(name.split("_")[1]); delta = self._frame(c).diff()
            up = delta.clip(lower=0).rolling(w).mean(); down = (-delta.clip(upper=0)).rolling(w).mean()
            rsi = 100 - 100 / (1 + up / down.replace(0, np.nan))
            return ((50 - rsi) / 50).to_numpy()
        if name.startswith("bollinger_"):
            return -self._z(c, int(name.split("_")[1]))
        if name.startswith("vwapdev_"):
            w = int(name.split("_")[1]); pv = self._frame(c * v).rolling(w).sum(); vv = self._frame(v).rolling(w).sum()
            return (-(self._frame(c) / (pv / vv) - 1)).to_numpy()
        if name.startswith("donchian_"):
            w = int(name.split("_")[1]); prior_h = self._frame(h).shift(1).rolling(w).max(); prior_l = self._frame(l).shift(1).rolling(w).min()
            return ((self._frame(c) - (prior_h + prior_l) / 2) / (prior_h - prior_l).replace(0, np.nan)).to_numpy()
        if name.startswith("atrbreak_"):
            w = int(name.split("_")[1]); mean = self._frame(c).shift(1).rolling(w).mean()
            return ((self._frame(c) - mean) / self._atr(w)).to_numpy()
        if name.startswith("rangepos_"):
            w = int(name.split("_")[1]); hi = self._frame(h).shift(1).rolling(w).max(); lo = self._frame(l).shift(1).rolling(w).min()
            return ((self._frame(c) - lo) / (hi - lo).replace(0, np.nan) - .5).to_numpy()
        if name.startswith("volumez_"):
            return self._z(np.log1p(v), int(name.split("_")[1]))
        if name.startswith("obv_"):
            w = int(name.split("_")[1]); signed = np.sign(np.vstack([np.zeros(c.shape[1]), np.diff(c, axis=0)])) * v
            obv = np.cumsum(signed, axis=0)
            return self._frame(obv).diff(w).to_numpy() / self._frame(v).rolling(w).sum().to_numpy()
        if name.startswith("cmf_"):
            w = int(name.split("_")[1]); mult = ((c - l) - (h - c)) / np.where(h == l, np.nan, h - l)
            return (self._frame(mult * v).rolling(w).sum() / self._frame(v).rolling(w).sum()).to_numpy()
        if name.startswith("atrpct_"):
            return -(self._atr(int(name.split("_")[1])) / c)
        if name.startswith("realvol_"):
            w = int(name.split("_")[1]); return -self._frame(c).pct_change().rolling(w).std(ddof=0).to_numpy()
        if name.startswith("volratio_"):
            w = int(name.split("_")[1]); returns = self._frame(c).pct_change()
            return (returns.rolling(max(3, w // 4)).std(ddof=0) / returns.rolling(w).std(ddof=0).replace(0, np.nan) - 1).to_numpy()
        if name.startswith("relative_") or name.startswith("betaadj_"):
            w = int(name.split("_")[1]); ret = self._frame(c).pct_change(w).to_numpy()
            count = np.sum(np.isfinite(ret), axis=1, keepdims=True)
            mean = np.divide(np.nansum(ret, axis=1, keepdims=True), count, out=np.zeros((len(ret), 1)), where=count > 0)
            return ret - mean
        if name == "macro_risk":
            symbol_index = {s: i for i, s in enumerate(self.data.symbols)}
            out = np.zeros_like(c)
            bond_symbol = "TLT" if "TLT" in symbol_index else ("IEF" if "IEF" in symbol_index else None)
            required = {"SPY", "QQQ", "UUP", "GLD"}
            if bond_symbol and required.issubset(symbol_index):
                ret = self._frame(c).pct_change(20).to_numpy()
                regime = (
                    ret[:, symbol_index["SPY"]] + ret[:, symbol_index["QQQ"]]
                    - ret[:, symbol_index[bond_symbol]] - ret[:, symbol_index["UUP"]]
                    - .5 * ret[:, symbol_index["GLD"]]
                )
                risk_assets = {"AAPL", "MSFT", "NVDA", "AMZN", "SPY", "QQQ", "IBIT", "BITX"}
                inverse_assets = {"BITI", bond_symbol, "UUP", "GLD"}
                for j, symbol in enumerate(self.data.symbols):
                    loading = 1.0 if symbol in risk_assets else (-1.0 if symbol in inverse_assets else 0.0)
                    out[:, j] = regime * loading
            elif {"SPY", "QQQ", "GLD", "SLV"}.issubset(symbol_index) and (
                "IBIT" in symbol_index or "BITX" in symbol_index
            ):
                # Reduced macro universe: equity/BTC risk appetite versus
                # precious metals and the inverse BTC ETF. All inputs are
                # trailing returns and are acted on from the next bar.
                ret = self._frame(c).pct_change(20).to_numpy()
                btc_symbol = "IBIT" if "IBIT" in symbol_index else "BITX"
                regime = (
                    .5 * (ret[:, symbol_index["SPY"]] + ret[:, symbol_index["QQQ"]])
                    + ret[:, symbol_index[btc_symbol]]
                    - .5 * (ret[:, symbol_index["GLD"]] + ret[:, symbol_index["SLV"]])
                )
                risk_assets = {"SPY", "QQQ", "IBIT", "BITX"}
                defensive_assets = {"GLD", "SLV", "BITI"}
                for j, symbol in enumerate(self.data.symbols):
                    loading = 1.0 if symbol in risk_assets else (-1.0 if symbol in defensive_assets else 0.0)
                    out[:, j] = regime * loading
            return out
        if name == "sentiment":
            return np.zeros_like(c) if self.data.sentiment is None else self.data.sentiment
        if name == "breaking_sentiment":
            if self.data.sentiment is None:
                return np.zeros_like(c)
            breaking = np.zeros_like(c) if self.data.breaking is None else self.data.breaking
            return self.data.sentiment * (1 + breaking)
        if name == "news_momentum":
            if self.data.sentiment is None:
                return np.zeros_like(c)
            return self._frame(self.data.sentiment).ewm(span=5, adjust=False).mean().to_numpy()
        raise KeyError(f"알 수 없는 지표: {name}")


INDICATOR_GROUPS: dict[str, tuple[str, ...]] = {
    "trend": ("ema_3_15", "ema_5_20", "ema_8_30", "roc_10", "roc_30", "momentum_20", "slope_20"),
    "mean_reversion": ("zclose_10", "zclose_20", "zclose_60", "rsi_7", "rsi_14", "bollinger_20", "vwapdev_20"),
    "breakout": ("donchian_10", "donchian_20", "donchian_60", "atrbreak_14", "rangepos_20"),
    "volume": ("volumez_20", "volumez_60", "obv_20", "cmf_20"),
    "volatility": ("atrpct_14", "realvol_20", "volratio_60"),
    "relative_macro": ("relative_10", "relative_30", "betaadj_20", "macro_risk"),
    "point_in_time_news": ("sentiment", "breaking_sentiment", "news_momentum"),
}

