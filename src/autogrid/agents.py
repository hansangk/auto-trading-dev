from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Review:
    verdict: str
    reasons: tuple[str, ...]


def thesis(row: dict) -> Review:
    return Review("PROPOSE", (
        f"홀드아웃 수익률 {row.get('total_return', 0):.2%}",
        f"Sharpe {row.get('sharpe', 0):.2f}, PF {row.get('profit_factor', 0):.2f}",
        "롱·숏 동시 바스켓과 다음 봉 체결 규칙 적용",
    ))


def antithesis(row: dict) -> Review:
    problems = []
    if row.get("trades", 0) < 300: problems.append("거래 수 300 미만")
    if row.get("max_drawdown", 1) > .05: problems.append("최대낙폭 5% 초과")
    if row.get("fold_positive_rate_validation", row.get("fold_positive_rate", 0)) < .6: problems.append("양의 수익 fold 60% 미만")
    if row.get("return_cost_x1.5", 1) <= 0: problems.append("비용 1.5배에서 손실")
    if row.get("long_pnl", 0) <= 0 or row.get("short_pnl", 0) <= 0: problems.append("롱/숏 한쪽 성과 음수")
    if row.get("uses_point_in_time_news", False):
        if row.get("news_incremental_return", 0) <= 0: problems.append("뉴스 제거 대비 증분성과 없음")
        if row.get("return_delay_2bar", 0) <= 0: problems.append("뉴스 2분 지연 시 성과 소멸")
    return Review("CHALLENGE" if problems else "PASS", tuple(problems or ["자동 탈락 사유 없음"]))


def synthesis(row: dict) -> Review:
    challenge = antithesis(row)
    if challenge.verdict == "PASS": return Review("ACCEPT_FOR_PAPER_TEST", ("검증·홀드아웃·스트레스 기준 통과",))
    if len(challenge.reasons) == 1: return Review("HOLD", challenge.reasons)
    return Review("REJECT", challenge.reasons)
