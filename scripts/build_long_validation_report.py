from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TIMEFRAMES = (30, 45, 60)


def pct(value: float) -> str:
    return f"{value * 100:+.3f}%"


def classify(row: pd.Series) -> tuple[str, str]:
    core = (
        row.full_return > 0
        and row.full_cost_x2_return > 0
        and row.full_delay_1bar_return > 0
        and row.full_delay_2bar_return > 0
        and row.full_long_pnl > 0
        and row.full_short_pnl > 0
        and row.full_profit_factor >= 1.10
        and row.random_positive_rate >= 0.65
        and row.random_cost_x2_positive_rate >= 0.55
        and row.full_max_drawdown <= 0.03
    )
    if bool(row.eligible):
        return "통과", "엄격 기준 통과"
    if core:
        return "조건부 연구", "독립 라운드·장기 일관성 부족"
    reasons: list[str] = []
    if row.full_return <= 0:
        reasons.append("잠금 OOS≤0")
    if row.full_cost_x2_return <= 0:
        reasons.append("비용×2≤0")
    if min(row.full_delay_1bar_return, row.full_delay_2bar_return) <= 0:
        reasons.append("지연≤0")
    if min(row.full_long_pnl, row.full_short_pnl) <= 0:
        reasons.append("롱/숏 한쪽≤0")
    if row.full_profit_factor < 1.10:
        reasons.append("PF<1.10")
    return "탈락", ", ".join(reasons[:3]) or "안정성 기준 미달"


def main() -> None:
    frames = []
    for minutes in TIMEFRAMES:
        frame = pd.read_csv(ROOT / f"runs/random_final_{minutes}m/random_validation.csv")
        frame["timeframe_min"] = minutes
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)
    decisions = combined.apply(classify, axis=1)
    combined["decision"] = [item[0] for item in decisions]
    combined["decision_reason"] = [item[1] for item in decisions]
    combined["independent_rounds"] = (
        combined.full_trades / (combined.long_k + combined.short_k)
    ).round().astype(int)
    combined["core_positive_count"] = (
        (combined.full_return > 0).astype(int)
        + (combined.full_cost_x2_return > 0).astype(int)
        + (combined.full_delay_1bar_return > 0).astype(int)
        + (combined.full_delay_2bar_return > 0).astype(int)
        + (combined.full_long_pnl > 0).astype(int)
        + (combined.full_short_pnl > 0).astype(int)
    )
    decision_order = {"통과": 2, "조건부 연구": 1, "탈락": 0}
    combined["decision_order"] = combined.decision.map(decision_order)
    combined = combined.sort_values(
        ["decision_order", "core_positive_count", "random_score", "full_return", "strategy_id"],
        ascending=[False, False, False, False, True],
    ).reset_index(drop=True)
    combined.insert(0, "overall_rank", range(1, len(combined) + 1))
    top30 = combined.head(30).copy()
    export_columns = [
        "overall_rank", "timeframe_min", "strategy_id", "decision", "decision_reason",
        "indicators", "weights", "long_k", "short_k", "hold_bars", "stop_loss_bps",
        "take_profit_multiple", "cooldown_bars", "full_return", "full_cost_x2_return",
        "full_delay_1bar_return", "full_delay_2bar_return", "full_trades", "independent_rounds",
        "full_win_rate", "full_profit_factor", "full_max_drawdown", "full_long_pnl",
        "full_short_pnl", "full_bitcoin_etf_pnl", "random_windows", "random_positive_rate",
        "random_cost_x2_positive_rate", "random_delay_positive_rate", "random_median_return",
        "random_q10_return", "random_worst_return", "random_score",
    ]
    top30[export_columns].to_csv(ROOT / "LONG_RANDOM_TOP30.csv", index=False)

    raw_counts = {}
    ranges = {}
    for year in (2024, 2025, 2026):
        raw = pd.read_csv(ROOT / f"data/alpaca_iex/raw_{year}.csv", usecols=["timestamp"])
        raw_counts[year] = len(raw)
    for minutes in TIMEFRAMES:
        market = pd.read_csv(ROOT / f"data/alpaca_iex/market_final_{minutes}m.csv", usecols=["timestamp"])
        ts = pd.to_datetime(market.timestamp, utc=True)
        ranges[minutes] = (ts.min(), ts.max(), ts.dt.date.nunique(), ts.nunique())

    best = top30.iloc[0]
    original = pd.read_csv(ROOT / "runs/final_45m/top30.csv")
    original_best = original[original.strategy_id.astype(str) == str(best.strategy_id)].iloc[0]
    detail = pd.read_csv(ROOT / "runs/random_final_45m/random_windows_detail.csv")
    detail = detail[detail.strategy_id.astype(str) == str(best.strategy_id)]
    by_window = detail.groupby("window_days").agg(
        windows=("return", "size"),
        positive_rate=("return", lambda x: (x > 0).mean()),
        cost2_positive_rate=("return_cost_x2", lambda x: (x > 0).mean()),
        median_return=("return", "median"),
        worst_return=("return", "min"),
    )

    lines = [
        "# 장기 랜덤구간 검증 보고서",
        "",
        "## 결론",
        "",
        "**실전 통과 전략은 0개다.** 3만 개 후보(30·45·60분봉 각 1만 개)를 탐색했지만, "
        "잠금 OOS·비용 2배·1/2봉 지연·롱/숏 양쪽 수익·최소 표본을 모두 만족한 전략은 없었다.",
        "",
        f"조건부 연구 1순위는 45분봉 `{best.strategy_id}` (`zclose_10` 40% + `OBV_20` 60%)다. "
        f"최종 60거래일 수익률 {pct(best.full_return)}, 승률 {best.full_win_rate * 100:.1f}%, "
        f"PF {best.full_profit_factor:.2f}, MDD {best.full_max_drawdown * 100:.3f}%였다. "
        f"비용 2배 후 수익은 {pct(best.full_cost_x2_return)}로 거의 전부 소멸했고, "
        f"{best.independent_rounds:.0f}개 독립 라운드에 불과해 실전 승인하지 않는다.",
        "",
        "## 데이터와 검증 설계",
        "",
        f"- Alpaca 무료 IEX 1분봉: 총 {sum(raw_counts.values()):,}행 "
        f"(2024 {raw_counts[2024]:,} / 2025 {raw_counts[2025]:,} / 2026 {raw_counts[2026]:,})",
        f"- 유니버스: SPY, QQQ, GLD, SLV, IBIT, BITI, BITX (개별 우량주 제외)",
        f"- 전체 범위: {ranges[30][0].date()}~{ranges[30][1].date()}, {ranges[30][2]}거래일",
        "- 발견 구간: 2024-01-11~2026-08-20. 20거래일 walk-forward, 내부 holdout, 비용·지연 스트레스 사용",
        "- 완전 잠금 구간: 2026-08-21~2026-11-13, 60거래일. 이 구간은 후보 선정 후 한 번만 평가",
        "- 랜덤 평가: 잠금 구간 안에서 5/10/20/40거래일 창 96개를 고정 seed로 추출",
        "- 비용 가정: 수수료 0.3bp + 슬리피지 2.0bp, 별도 비용 2배 스트레스, 신호 1/2봉 지연",
        "- 주의: 랜덤 창은 서로 겹치므로 96개 독립 실험으로 해석하면 안 된다.",
        "",
        "## 1순위 조건부 연구 후보",
        "",
        f"- 파라미터: 롱 {int(best.long_k)}개·숏 {int(best.short_k)}개 동시, "
        f"{int(best.hold_bars)}봉 보유, 손절 {best.stop_loss_bps:.0f}bp, 익절 {best.take_profit_multiple:.0f}R, "
        f"쿨다운 {int(best.cooldown_bars)}봉",
        f"- 잠금 OOS: 수익 {pct(best.full_return)}, 비용×2 {pct(best.full_cost_x2_return)}, "
        f"1봉 지연 {pct(best.full_delay_1bar_return)}, 2봉 지연 {pct(best.full_delay_2bar_return)}",
        f"- 거래: 포지션 {int(best.full_trades)}건 / 독립 라운드 약 {int(best.independent_rounds)}회 / "
        f"승률 {best.full_win_rate * 100:.1f}% / PF {best.full_profit_factor:.2f}",
        f"- 롱 PnL {best.full_long_pnl:,.0f}원 / 숏 PnL {best.full_short_pnl:,.0f}원 / "
        f"비트코인 ETF PnL {best.full_bitcoin_etf_pnl:,.0f}원",
        f"- 랜덤 창: 양수 {best.random_positive_rate * 100:.1f}%, 비용×2 양수 "
        f"{best.random_cost_x2_positive_rate * 100:.1f}%, 1봉 지연 양수 {best.random_delay_positive_rate * 100:.1f}%",
        f"- 발견 구간 walk-forward 양수 비율 {original_best.fold_positive_rate_validation * 100:.1f}%, "
        f"최악 fold {pct(original_best.worst_fold_return_validation)}",
        "",
        "기간별 랜덤 창 성과:",
        "",
        "| 창 | 개수 | 양수율 | 비용×2 양수율 | 중앙 수익 | 최악 수익 |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for days, row in by_window.iterrows():
        lines.append(
            f"| {days}일 | {int(row.windows)} | {row.positive_rate * 100:.1f}% | "
            f"{row.cost2_positive_rate * 100:.1f}% | {pct(row.median_return)} | {pct(row.worst_return)} |"
        )
    lines.extend([
        "",
        "이 전략은 60일 잠금 구간에서는 좋아 보이지만, 비용을 두 배로 하면 수익이 사실상 0이고 "
        "핵심 지표 OBV가 부분 거래량인 IEX에 의존한다. 또 비트코인 ETF 하위 손익이 음수다. "
        "따라서 페이퍼 운용도 추가 검증 뒤로 미룬다.",
        "",
        "## OOS 강건성 기준 1~30위",
        "",
        "아래 순위는 실전 승인 순위가 아니라 추가 연구 우선순위다.",
        "",
        "| 순위 | 봉 | 전략 | 지표 | OOS 수익 | 승률 | PF | MDD | 비용×2 | 최악 지연 | 랜덤 양수율 | 라운드 | 판정 |",
        "|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ])
    for _, row in top30.iterrows():
        indicators = str(row.indicators).replace("'", "")
        lines.append(
            f"| {int(row.overall_rank)} | {int(row.timeframe_min)}m | `{row.strategy_id}` | {indicators} | "
            f"{pct(row.full_return)} | {row.full_win_rate * 100:.1f}% | {row.full_profit_factor:.2f} | "
            f"{row.full_max_drawdown * 100:.2f}% | {pct(row.full_cost_x2_return)} | "
            f"{pct(min(row.full_delay_1bar_return, row.full_delay_2bar_return))} | "
            f"{row.random_positive_rate * 100:.1f}% | {int(row.independent_rounds)} | {row.decision} |"
        )
    lines.extend([
        "",
        "## 정·반·합 평가",
        "",
        "- **정:** 45분봉 1순위는 30/60분봉보다 비용·지연·랜덤 구간 안정성이 낫고 롱·숏 PnL이 모두 양수다.",
        "- **반:** 비용×2에서 수익의 약 98%가 사라지고, 독립 라운드는 60회뿐이다. IEX 거래량 기반 OBV, "
        "겹치는 랜덤 창, 3만 회 다중탐색 때문에 우연 생존 가능성이 크다.",
        "- **합:** 조건부 연구 후보 1개만 보류하고 실전·페이퍼 승인은 0개로 유지한다. "
        "BITO로 2021년 이후를 늘리고 SIP 데이터와 새 잠금 6개월에서 재검증한다.",
        "",
        "## 자금 보호 권고",
        "",
        "- 현재: 1억원 가상자금만 사용, 실제 투입 0원",
        "- 향후 모든 관문 통과 후: 500만~1,000만원, 무레버리지, gross 50% 이하",
        "- 라운드당 위험 0.05%, 일일 hard stop 0.5%, 주간 1%, 30일 2%, 시스템 MDD 3%에서 전면 중지",
        "- 주문 거부·시세 지연·포지션 불일치 시 신규 주문 차단 후 시장가 청산. 손실 0은 보장할 수 없다.",
        "",
        "## 다음 검증",
        "",
        "1. BITO를 포함해 2021년 이후 데이터로 연장하고, 인버스·레버리지 ETF는 그룹 노출을 제한한다.",
        "2. 24개월 학습→3개월 검증→3개월 시험을 반복하고 마지막 6개월은 완전히 잠근다.",
        "3. 거래 수 대신 독립 라운드 100회 이상을 요구하고, 45분봉 후보 파라미터는 현재 잠금 결과에 맞춰 조정하지 않는다.",
        "4. SIP 또는 틱·호가 데이터로 OBV와 실제 체결 비용을 재검증한다.",
        "5. 뉴스/매크로는 point-in-time `available_at` 원본을 확보한 뒤에만 추가한다. 현재 결과에는 뉴스 알파가 포함되지 않았다.",
        "",
        "이 보고서는 연구 결과이며 수익을 보장하거나 매매를 권유하지 않는다.",
    ])
    (ROOT / "LONG_RANDOM_VALIDATION_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
