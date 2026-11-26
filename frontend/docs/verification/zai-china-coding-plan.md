# 中国站 Coding Plan 切换与绑定后隔离复核

## 中国站切换

- 后端凭据类型显示名及前端中英文提示改为中国站。
- 默认 OpenAI Chat Completions 基础地址改为 `https://open.bigmodel.cn/api/coding/paas/v4`。
- Key 管理链接使用智谱中国站个人编程套餐入口。
- 保留类型标识 `zai_coding_credential`，模型目录与会话引用不变。
- 已有「智谱」凭据的国际站地址已迁移，凭据 ID、API Key 及其他字段均保留；其余 31 个业务键与绑定时的摘要一致。
- 后端已重启，真实服务的凭据 Schema 和已保存凭据地址均验证通过。
- 4 项协议测试、6 项认证测试、TypeScript 和改动组件 ESLint 通过。协议测试使用离线 HTTP 响应，没有调用付费模型 API。
- 页面验收见 [zai-china-coding-plan.jpg](./zai-china-coding-plan.jpg)。

依据：[智谱中国站接入文档](https://docs.bigmodel.cn/cn/coding-plan/tool/others)。

## molldy 绑定后隔离复核

在上述凭据迁移前，对当前真实后端执行 118 项接口检查，全部通过：

1. `molldy` 仍映射到旧身份 `study`，两个旧工作区目录映射保留。
2. 通过注册、登录接口创建两个临时账号，其中一个用户名故意设为 `study`；新账号业务身份均为各自 UUID，不能认领旧身份。
3. 新账号的智能体、凭据、知识库、MCP、Skill 列表为空。
4. 猜测旧资源 ID、读取旧智能体会话、会话消息和状态、知识库文档及检索、工作区 MCP 和文件均返回 404。
5. 按旧 ID 提交凭据或 MCP 更新探测返回 404，没有改写原记录。
6. 伪造旧身份头、账号 ID、重复身份头及 URL 用户参数不能切换身份；匿名伪造身份访问返回 401。
7. 使用原用户真实生成的文件下载 Token，也无法跨用户读取文件。
8. 检查期间 32 个业务键和 99 个工作区、文档、向量文件的摘要完全一致。临时账号、登录会话均已清理。

这确认了业务 HTTP 接口的隔离。本地 Shell 和本机 MCP 仍使用宿主机权限，不能据此声称已实现对不可信用户的操作系统级隔离。

详细状态码在 `backend/.tmp/isolation-check-result.json`；端点迁移结果在 `backend/.tmp/zai-china-migration-result.json`，报告不含 Key 和消息正文。
