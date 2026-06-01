# AI Assignment Assistant 用户版

这是给普通用户下载使用的本地版本。

## 怎么用

1. 解压 `AI-Assignment-Assistant-user.zip`。
2. 双击 `run_windows.bat`。
3. 等浏览器打开本地页面。
4. 上传你的课件和题目。
5. 如果要生成完整答案，在左侧填写：
   - API Key
   - Base URL
   - Model

如果不填写 API，也可以生成“本地证据草稿”。

## 课件会上传吗？

不会。

课件只保存在你电脑本地的 `app_workspace/` 里，不会上传到 GitHub。

## 图片题目

如果题目是截图、照片或扫描图片，请选择支持图片输入的模型。

纯文本模型只能处理文字，不能看图片。

## 本地配置

你在页面里保存的 API 配置会写到：

```text
.local_config.json
```

这个文件只在你的电脑上，不要分享给别人。
