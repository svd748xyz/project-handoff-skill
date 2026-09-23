"""Create fictional process evidence and review it; network requires --live."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "project-handoff" / "scripts"))
import process_handoff as process


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--live", action="store_true", help="Send these fictional fixtures to Jev using existing account access")
    args = parser.parse_args()
    out = process.safe_path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    project_id = str(uuid.uuid4())
    context = {"project_id": project_id, "goal": "修复 CSV 解析器并保留空输入诊断；本演示的所有记录均为虚构。",
               "boundaries": ["只做本地验证。生产系统尚未验收，禁止把静态测试等同业务验收。"],
               "next_action": "核实空输入测试和当前失败，生成不夸大验收结果的交接。"}
    (out / "context.json").write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = [
        ("requirements-01", "requirements", "user_constraint", "unknown", "用户约束：只能本地测试。没有授权发布或生产操作。", None),
        ("discovery-01", "discovery", "tool_result", "success", "目录颜色主题为蓝色。", None),
        ("implementation-01", "implementation", "claim", "success", "local parser empty-input test: PASS", "本地解析器空输入测试通过。"),
        ("verification-01", "verification", "claim", "failure", "local parser malformed-header test: FAIL; expected diagnostic E_HEADER; actual unhandled exception", "本地解析器非法表头测试通过。"),
        ("handoff-01", "handoff", "claim", "success", "Static type check: PASS. Report scope: source type checks only.", "业务用户已经验收生产环境。"),
        ("handoff-memory-01", "handoff", "claim", "success", "Static type check: PASS. Report scope: source type checks only.", "解析器运行时峰值内存低于 10 MB。"),
        ("resume-01", "resume", "blocker", "unknown", "待确认：尚缺业务验收记录；下一步仅修复非法表头报错，验收条件为该用例通过。", None),
    ]
    for event_id, stage, kind, outcome, excerpt, claim in rows:
        source = out / (event_id + ".txt")
        source.write_text(excerpt, encoding="utf-8")
        event = {"id": event_id, "project_id": project_id, "stage": stage, "kind": kind,
                 "source": source.name, "observed_at": datetime.now(timezone.utc).isoformat(),
                 "scope": "Synthetic fixture only. These are not real project test/acceptance results.",
                 "excerpt": excerpt, "outcome": outcome}
        if claim:
            event["claim"] = claim
        process.record_event(out / "store", event)
    mode = "live" if args.live else "offline"
    report = process.review_events(out / "store", context, out / "review", mode)
    summary = {"mode": mode, "model_review_incomplete": report["model_review_incomplete"],
               "review_counts": report["review_counts"], "live_usage": report["live_usage"],
               "claim_results": {d["id"]: d["claim_review"]["choice"] if d["claim_review"] else None
                                 for d in report["decisions"] if d["claim"]}}
    # Expected labels are for the evaluator only, never included in model state.
    expected = {"implementation-01": "supported", "verification-01": "contradicted",
                "handoff-01": "contradicted", "handoff-memory-01": "insufficient"}
    summary["fixture_matches"] = {key: summary["claim_results"][key] == value for key, value in expected.items()} if args.live else None
    (out / "demo-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not args.live or not report["model_review_incomplete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
