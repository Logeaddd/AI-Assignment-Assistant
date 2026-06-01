from __future__ import annotations

import os
import shutil
import sys
import tempfile
import base64
import json
from pathlib import Path

import streamlit as st

import harness as h


APP_DIR = Path(__file__).resolve().parent
WORK_DIR = APP_DIR / "app_workspace"
LOCAL_CONFIG = APP_DIR / ".local_config.json"


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


def image_to_data_url(path: Path) -> str:
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "application/octet-stream")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def save_question_images(files) -> list[Path]:
    image_dir = WORK_DIR / "question_images"
    image_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for idx, file in enumerate(files, 1):
        safe_name = Path(file.name).name
        target = image_dir / f"{idx:02}_{safe_name}"
        target.write_bytes(file.getbuffer())
        saved.append(target)
    return saved


def load_local_config() -> dict:
    if not LOCAL_CONFIG.exists():
        return {}
    try:
        return json.loads(LOCAL_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_local_config(config: dict) -> None:
    # Local convenience only. This file is ignored by git.
    LOCAL_CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def call_model(prompt: str, api_key: str, base_url: str, model: str, image_paths: list[Path] | None = None) -> str:
    from openai import OpenAI

    kwargs = {"api_key": api_key}
    if base_url.strip():
        kwargs["base_url"] = base_url.strip()
    client = OpenAI(**kwargs)
    image_paths = image_paths or []

    try:
        if image_paths:
            content = [{"type": "input_text", "text": prompt}]
            for image_path in image_paths:
                content.append({"type": "input_image", "image_url": image_to_data_url(image_path)})
            response = client.responses.create(
                model=model,
                input=[{"role": "user", "content": content}],
            )
        else:
            response = client.responses.create(model=model, input=prompt)
        return response.output_text
    except Exception as responses_error:
        try:
            if image_paths:
                content = [{"type": "text", "text": prompt}]
                for image_path in image_paths:
                    content.append({"type": "image_url", "image_url": {"url": image_to_data_url(image_path)}})
                messages = [{"role": "user", "content": content}]
            else:
                messages = [{"role": "user", "content": prompt}]
            response = client.chat.completions.create(
                model=model,
                messages=messages,
            )
            return response.choices[0].message.content or ""
        except Exception as chat_error:
            raise RuntimeError(
                "Model call failed. Responses API error: "
                f"{type(responses_error).__name__}: {responses_error}; "
                "chat.completions fallback error: "
                f"{type(chat_error).__name__}: {chat_error}"
            ) from chat_error


def build_answer_doc(kb: h.KnowledgeBase, questions: list[dict], settings: dict) -> str:
    sections: list[str] = []
    for idx, item in enumerate(questions, 1):
        question = item["text"]
        image_paths = item.get("image_paths", [])
        retrieval_text = question if item["type"] == "text" else item.get("retrieval_text", "")
        evidence = h.retrieve(kb.blocks, retrieval_text, settings["top_k"]) if retrieval_text else []
        verdict = h.assess_grounding(retrieval_text or question, evidence, kb)
        banner = h.provenance_banner(verdict)
        image_list = "\n".join(f"- {p}" for p in image_paths)
        question_recap = f"## 题目复述\n{question}"
        if image_paths:
            question_recap += f"\n\n题目图片：\n{image_list}"

        if settings["use_model"]:
            prompt = h.make_prompt(question, evidence, kb, settings["external_context"], verdict)
            if image_paths:
                prompt += (
                    "\n\n题目以图片形式提供。请先读取图片题干并在“题目复述”中复述完整题目；"
                    "如果图片内容识别不清，必须明确说明。"
                )
            answer = call_model(prompt, settings["api_key"], settings["base_url"], settings["model"], image_paths)
        else:
            if image_paths:
                answer = (
                    "## 标准答案草稿\n"
                    "题目以图片形式提供。离线模式不能可靠识别图片题干；请交给支持图片输入的模型/agent，"
                    "或手动补充文字题目。\n\n"
                    "## 资料不一致风险\n"
                    "- 当前未读取图片内容，不能生成真实答案。\n"
                )
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
    st.caption("基于课件生成合规标准答案；可交给 agent 使用，也可填自己的兼容 API。")
    local_config = load_local_config()

    with st.sidebar:
        st.header("模型设置")
        run_mode = st.radio(
            "使用方式",
            [
                "本地证据草稿（不填 API）",
                "填写 API 生成完整答案",
            ],
            index=0,
            help="普通用户选第二项并填写自己的 API；不填 API 时只生成课件证据草稿。Agent 使用请走命令行 harness，不需要打开这个网页。"
        )
        use_model = run_mode == "填写 API 生成完整答案"
        default_api_key = local_config.get("api_key") or os.getenv("OPENAI_API_KEY", "")
        default_base_url = local_config.get("base_url") or os.getenv("OPENAI_BASE_URL", "")
        default_model = local_config.get("model") or os.getenv("STANDARD_ANSWER_MODEL", "gpt-4.1-mini")

        with st.expander("填写 API Key / URL / 模型", expanded=use_model):
            api_key = st.text_input("API Key", type="password", value=default_api_key)
            base_url = st.text_input("Base URL（OpenAI 可留空；兼容服务填写自己的 URL）", value=default_base_url)
            model = st.text_input("Model（图片题请选择支持图片输入的模型）", value=default_model)
            if st.button("保存到本机配置"):
                save_local_config({"api_key": api_key, "base_url": base_url, "model": model})
                st.success("已保存到本机 .local_config.json（不会提交到仓库）")
        st.info("图片题、扫描 PDF 页图、截图题需要支持图片输入的模型；纯文本模型只能处理抽取出来的文字。")
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
            "文字题目（可选）：每题之间空一行，或用 1. / 2. 编号",
            height=220,
            value="",
        )
        question_image_uploads = st.file_uploader(
            "题目图片（可选，可多张）：截图、照片、扫描题都可以",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
        )
        question_images: list[Path] = []
        if question_image_uploads:
            question_images = save_question_images(question_image_uploads)
            st.write("题目图片预览：")
            for p in question_images:
                st.image(str(p), caption=p.name, use_container_width=True)
            st.caption("图片题目需要支持图片输入的模型，或交给能看图的 agent。")
        combine_images = st.checkbox("把多张题目图片合并为一道题", value=True)
        external_context = st.text_area("可选：外部补充资料", height=120)

    with col_right:
        st.subheader("3. 生成答案")
        if st.button("构建知识库并生成", type="primary"):
            if not saved_files:
                st.error("请先上传课件。")
                return
            if use_model and (not api_key.strip() or not model.strip()):
                st.error("填写 API 生成完整答案需要 API Key 和 Model。本地证据草稿模式不需要 key。")
                return
            text_questions = split_questions(questions_text) if questions_text.strip() else []
            questions = [{"type": "text", "text": q, "image_paths": []} for q in text_questions]
            if question_images and combine_images:
                questions.append({
                    "type": "image",
                    "text": "图片题目：请按顺序读取所有上传的题目图片并作答。",
                    "retrieval_text": questions_text.strip(),
                    "image_paths": question_images,
                })
            elif question_images:
                for idx, image_path in enumerate(question_images, 1):
                    questions.append({
                        "type": "image",
                        "text": f"图片题目 {idx}：请读取上传的题目图片并作答。",
                        "retrieval_text": questions_text.strip(),
                        "image_paths": [image_path],
                    })
            if not questions:
                st.error("请至少输入文字题目或上传题目图片。")
                return
            if question_images and use_model:
                st.info("检测到题目图片：请确认所选模型支持图片输入。")
            if question_images and not use_model:
                st.warning("当前是默认/离线模式，app 不会识别题目图片；输出会提示交给支持图片输入的 agent 或模型。")

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
