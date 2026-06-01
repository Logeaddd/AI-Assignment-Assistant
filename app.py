from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import streamlit as st

import harness as h


APP_DIR = Path(__file__).resolve().parent
WORK_DIR = APP_DIR / "app_workspace"


def save_uploads(files) -> list[Path]:
    upload_dir = WORK_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for file in files:
        # Keep only the filename; Streamlit uploads are not trusted paths.
        safe_name = Path(file.name).name
        target = upload_dir / safe_name
        target.write_bytes(file.getbuffer())
        saved.append(target)
    return saved


def call_model(prompt: str, api_key: str, base_url: str, model: str) -> str:
    from openai import OpenAI

    kwargs = {"api_key": api_key}
    if base_url.strip():
        kwargs["base_url"] = base_url.strip()
    client = OpenAI(**kwargs)

    try:
        response = client.responses.create(model=model, input=prompt)
        return response.output_text
    except Exception as responses_error:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content or ""
        except Exception as chat_error:
            raise RuntimeError(
                "Model call failed. Responses API error: "
                f"{type(responses_error).__name__}: {responses_error}; "
                "chat.completions fallback error: "
                f"{type(chat_error).__name__}: {chat_error}"
            ) from chat_error


def build_answer_doc(kb: h.KnowledgeBase, questions: list[str], settings: dict) -> str:
    sections: list[str] = []
    for idx, question in enumerate(questions, 1):
        evidence = h.retrieve(kb.blocks, question, settings["top_k"])
        verdict = h.assess_grounding(question, evidence, kb)
        banner = h.provenance_banner(verdict)
        question_recap = f"## 题目复述\n{question}"

        if settings["use_model"]:
            prompt = h.make_prompt(question, evidence, kb, settings["external_context"], verdict)
            answer = call_model(prompt, settings["api_key"], settings["base_url"], settings["model"])
        else:
            answer = h.offline_answer(question, evidence, kb, verdict)

        findings = h.compliance_check(answer, evidence, kb, verdict)
        blocked = [f for f in findings if f.severity == "block"]
        sev_label = {"block": "拦截", "warn": "提示", "info": "说明"}
        finding_text = (
            "\n".join(f"- [{sev_label[f.severity]}] {f.message}" for f in findings)
            if findings
            else "- 未发现明显偏离课件的问题。"
        )
        gate = "**未通过（存在拦截项，请勿直接作为标准答案发布）**" if blocked else "通过"

        sections.append(
            f"# 第 {idx} 题\n\n{question_recap}\n\n{banner}\n\n{answer}\n\n"
            f"## Harness 合规校验\n- 合规闸门：{gate}\n{finding_text}\n"
        )
    return "\n\n".join(sections)


def split_questions(text: str) -> list[str]:
    tmp = tempfile.NamedTemporaryFile("w", delete=False, suffix=".md", encoding="utf-8")
    try:
        tmp.write(text)
        tmp.close()
        return h.read_questions(Path(tmp.name))
    finally:
        Path(tmp.name).unlink(missing_ok=True)


def main() -> None:
    st.set_page_config(page_title="AI Assignment Assistant", layout="wide")
    st.title("AI Assignment Assistant")
    st.caption("基于课件生成合规标准答案；允许 AI 补全，但必须标注可能与资料不一致。")

    with st.sidebar:
        st.header("模型设置")
        use_model = st.toggle("调用模型生成完整答案", value=False)
        api_key = st.text_input("API Key", type="password", value=os.getenv("OPENAI_API_KEY", ""))
        base_url = st.text_input("Base URL", value=os.getenv("OPENAI_BASE_URL", ""))
        model = st.text_input("Model", value=os.getenv("STANDARD_ANSWER_MODEL", "gpt-4.1-mini"))
        top_k = st.number_input("检索证据数量", min_value=1, max_value=20, value=6)

        st.header("工作区")
        if st.button("清空本地工作区"):
            if WORK_DIR.exists():
                shutil.rmtree(WORK_DIR)
            st.success("已清空")

    col_left, col_right = st.columns([0.42, 0.58])

    with col_left:
        st.subheader("1. 上传课件")
        uploads = st.file_uploader(
            "支持 PDF / DOCX / PPTX / TXT / MD",
            type=["pdf", "docx", "pptx", "txt", "md"],
            accept_multiple_files=True,
        )

        saved_files: list[Path] = []
        if uploads:
            saved_files = save_uploads(uploads)
            st.write("已保存：")
            for p in saved_files:
                st.code(str(p), language="text")

        if saved_files and st.button("诊断 PDF"):
            for p in saved_files:
                if p.suffix.lower() == ".pdf":
                    diag, low_pages, engine = h.diagnose_pdf_file(p)
                    st.markdown(f"**{p.name}**")
                    st.write(
                        {
                            "pages": diag.units_total,
                            "engine": engine,
                            "pages_with_text": diag.units_with_text,
                            "chars": diag.chars_extracted,
                            "text_ratio": round(diag.text_ratio, 3),
                            "likely_scanned": diag.likely_scanned,
                        }
                    )
                    if diag.likely_scanned:
                        st.warning("扫描/图片型 PDF：文本 harness 不可靠，请用页图/OCR/人工核对。")
                    if low_pages:
                        st.caption(f"低文本页示例：{', '.join(map(str, low_pages[:20]))}")

        if saved_files and st.button("准备 PDF 页图"):
            for p in saved_files:
                if p.suffix.lower() == ".pdf":
                    prep_dir = WORK_DIR / "prep" / h.safe_pdf_stem(p)
                    safe_pdf = h.prepare_pdf_path(p, prep_dir)
                    diag, _low_pages, _engine = h.diagnose_pdf_file(safe_pdf)
                    pages = list(range(max(1, diag.units_total - 2), diag.units_total + 1))
                    rendered = h.render_pdf_pages(safe_pdf, prep_dir / "rendered_last_pages", pages)
                    contacts = h.make_contact_sheets(safe_pdf, prep_dir / "contact")
                    st.success(f"已准备：{prep_dir}")
                    st.write(f"最后页图：{len(rendered)} 张；contact sheet：{len(contacts)} 张")
                    for ev in rendered:
                        st.image(ev.rendered_image_path, caption=f"{p.name} page {ev.page_number}", use_container_width=True)

        st.subheader("2. 输入题目")
        questions_text = st.text_area(
            "每题之间空一行，或用 1. / 2. 编号",
            height=220,
            value="1. 请在这里输入题目。",
        )
        external_context = st.text_area("可选：外部补充资料", height=120)

    with col_right:
        st.subheader("3. 生成答案")
        if st.button("构建知识库并生成", type="primary"):
            if not saved_files:
                st.error("请先上传课件。")
                return
            if use_model and (not api_key.strip() or not model.strip()):
                st.error("调用模型需要 API Key 和 Model。")
                return
            questions = split_questions(questions_text)
            if not questions:
                st.error("没有识别到题目。")
                return

            with st.status("构建知识库...", expanded=True) as status:
                kb = h.build_kb(saved_files)
                st.write(f"文本块：{len(kb.blocks)}")
                st.write(f"公式候选：{len(kb.formulas)}")
                st.write(f"格式规则：{len(kb.format_rules)}")
                for d in kb.diagnostics:
                    if d.likely_scanned:
                        st.warning(f"{Path(d.source).name}: 疑似扫描/图片型，文本接地不可靠。")
                    else:
                        st.info(f"{Path(d.source).name}: 文本层可用。")
                status.update(label="生成答案...", state="running")

                settings = {
                    "use_model": use_model,
                    "api_key": api_key,
                    "base_url": base_url,
                    "model": model,
                    "top_k": int(top_k),
                    "external_context": external_context,
                }
                try:
                    answer_doc = build_answer_doc(kb, questions, settings)
                except Exception as exc:
                    status.update(label="生成失败", state="error")
                    st.exception(exc)
                    return
                status.update(label="完成", state="complete")

            st.download_button(
                "下载 Markdown",
                data=answer_doc.encode("utf-8-sig"),
                file_name="answers.md",
                mime="text/markdown",
            )
            st.markdown(answer_doc)


if __name__ == "__main__":
    main()
