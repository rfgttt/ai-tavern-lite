# 一键自检

双击项目根目录的 `run-self-test.bat`。

工具会使用端口 `8765` 和临时数据库运行，不修改现有角色、会话、API Key 或 `backend/data`。默认会打开浏览器执行真实前端检查，并在项目根目录的 `self-test-results` 文件夹生成：

```text
ai-tavern-self-test-YYYYMMDD-HHMMSS.zip
```

把该 ZIP 上传即可定位失败模块。浏览器测试包括设置覆盖层返回、会话缓存、草稿和滚动位置、回复动态数据、说话人颜色及未知变量面板。
