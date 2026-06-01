"""Self-test: prove unlabeled AI supplementation is blocked, labeled supplementation is allowed."""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("h", HERE / "harness.py")
h = importlib.util.module_from_spec(spec)
sys.modules["h"] = h  # required so dataclass _is_type resolves
spec.loader.exec_module(h)

h._force_utf8_console()  # so Chinese findings are readable on legacy consoles

kb = h.KnowledgeBase(
    version=1,
    materials=["synthetic_scanned_formula_course.pdf"],
    blocks=[
        h.SourceBlock(
            source="synthetic_scanned_formula_course.pdf",
            locator="page 135",
            text="作业：写出带电粒子辐射角分布的一般公式，并推导其非相对论极限。",
        )
    ],
    formulas=[],
    format_rules=[],
    diagnostics=[
        h.MaterialDiagnostic(
            source="synthetic_scanned_formula_course.pdf",
            kind="pdf",
            units_total=135,
            units_with_text=7,
            chars_extracted=1431,
            text_ratio=0.05,
            likely_scanned=True,
            note="synthetic scanned-PDF diagnostic",
        )
    ],
)
q = "写出带电粒子辐射角分布的一般公式，并推导其非相对论极限。"
evidence = h.retrieve(kb.blocks, q, 6)
verdict = h.assess_grounding(q, evidence, kb)
print("verdict.level =", verdict.level, "| formula_q =", verdict.is_formula_question)

# Case A: a confident answer that pretends to be courseware-grounded and does
# NOT self-label risk. This MUST be blocked.
dishonest = (
    "## 题目复述\n写出带电粒子辐射角分布的一般公式，并推导其非相对论极限。\n"
    "## 标准答案\n根据课件，辐射角分布为 dP/dOmega = ... 。\n"
    "## 依据\n依据课件证据 [1]。\n"
)
findings_a = h.compliance_check(dishonest, evidence, kb, verdict)
blocks_a = [f for f in findings_a if f.severity == "block"]
print("\n[Case A: dishonest confident answer]")
for f in findings_a:
    print(f"  {f.severity}: {f.message}")
print("  -> blocked?", bool(blocks_a))

# Case B: same content but honestly self-labeled as model supplementation.
# This is allowed by the current policy.
honest = (
    "## 题目复述\n写出带电粒子辐射角分布的一般公式，并推导其非相对论极限。\n"
    "## 标准答案\n课件证据不足，以下公式为 [模型推导]：dP/dOmega = ... 。"
    "这部分可能与资料不一致，非课件直接依据。\n"
)
findings_b = h.compliance_check(honest, evidence, kb, verdict)
blocks_b = [f for f in findings_b if f.severity == "block"]
print("\n[Case B: honest self-labeled answer]")
for f in findings_b:
    print(f"  {f.severity}: {f.message}")
print("  -> blocked?", bool(blocks_b))

assert blocks_a, "FAIL: dishonest answer should have been blocked"
assert not blocks_b, "FAIL: honest answer should NOT have been blocked"
print("\nSELFTEST PASS: unlabeled supplementation is blocked; labeled AI supplementation is allowed.")
