# BudgetFlow · Slidev（paper1）

基于 [Slidev](https://github.com/slidevjs/slidev) 的演示稿；入口文件为 [`slides.md`](./slides.md)。

## 推荐：用 pnpm 安装并启动

本项目根目录已包含 **`.npmrc`**（`shamefully-hoist=true`），与 Slidev / Vite 的扁平依赖需求一致；**不要用错误的 `pnpm-workspace.yaml` 只写 `shamefullyHoist`**（那是 `.npmrc` 的配置项）。

```bash
# 若尚未安装 pnpm
npm i -g pnpm

cd slidev_paper1

# 首次或依赖变更后
pnpm install

# 启动开发服务器（会自动尝试打开浏览器）
pnpm dev
```

浏览器默认访问：**http://localhost:3030**（若端口占用，终端里会打印实际地址）。

其它常用命令：

```bash
pnpm run build    # 静态构建
pnpm run export   # 导出 PDF 等（可能需要额外安装 Playwright）
```

## 为何曾经出现 `slidev: not found`

在当前目录 **没有成功执行过 `pnpm install`**（或 `node_modules` 不完整）时，`node_modules/.bin/slidev` 不存在，脚本里的 `slidev` 就找不到。请先 **`cd` 到本目录** 再执行 **`pnpm install`**，然后 **`pnpm dev`**。

## 原生绑定 / optional 依赖报错（Linux x64）

若在启动时出现 **Cannot find native binding**、缺少 `@rolldown/binding-linux-x64-gnu` 或 `@oxc-parser/binding-linux-x64-gnu`，多半是 **optional 依赖未能自动装上**（老 npm bug、镜像或环境限制）。本项目已在 `package.json` 里 **显式依赖** 这两个 Linux x64 GNU 绑定包作为兜底；若升级 Slidev 后版本不匹配，可按报错里的包名与版本号对齐后执行：

```bash
pnpm add @rolldown/binding-linux-x64-gnu@<与 rolldown 一致的版本>
pnpm add @oxc-parser/binding-linux-x64-gnu@<与 oxc-parser 一致的版本>
```

## 仍使用 npm 时

可以删除 `pnpm-lock.yaml` 后使用 `npm install` / `npm run dev`，但不推荐与 pnpm 混用同一目录（不要同时保留两套 lockfile 来回切换）。

---

更多用法见 [Slidev 文档](https://sli.dev/)。
