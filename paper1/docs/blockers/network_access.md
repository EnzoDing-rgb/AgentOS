# 外网数据获取备忘

## 这份文件干嘛

以后如果这台 Linux 机器拉不到外网数据，先看这个。

当前已经验证过可行的方法是：

- 用 **main Mac** 的本地代理翻墙
- 再通过 **反向 SSH 端口转发**，把 Mac 的代理映射到这台 Linux
- 然后 Linux 侧临时设置 `http_proxy / https_proxy / all_proxy`

---

## 当前机器关系

- 本地工作机器：`hpc`
- main Mac Tailscale 地址：`100.72.121.78`
- hpc Tailscale 地址：`100.86.9.121`

注意：

- Linux 容器里的 `172.*` 内网地址不能直接给 Mac 用
- 要走 `hpc` 这个 Tailscale 地址

---

## 什么时候需要这个

当出现下面这些问题时：

- HuggingFace 数据集下载超时
- GitHub 某些外网资源拉不下来
- 公开 `.traj` / calibration 数据拿不到

如果本地已有数据，就不要折腾代理。

---

## 步骤 1：在 main Mac 上开反向端口转发

在 **main Mac terminal** 跑：

```bash
ssh -o RemoteCommand=none -T -N -R 49792:127.0.0.1:49792 root@100.86.9.121
```

前提：

- main Mac 本地代理已经开在 `127.0.0.1:49792`
- 这个 ssh 窗口必须保持打开

作用：

- 把 Mac 本地代理端口 `49792`
- 映射到 `hpc` 这边的 `127.0.0.1:49792`

---

## 步骤 2：Linux 上设置临时代理环境变量

在这台 Linux 机器上：

```bash
export https_proxy=http://127.0.0.1:49792
export http_proxy=http://127.0.0.1:49792
export all_proxy=socks5://127.0.0.1:49792
```

如果只想单次命令生效，也可以直接前缀：

```bash
HTTPS_PROXY=http://127.0.0.1:49792 \
HTTP_PROXY=http://127.0.0.1:49792 \
ALL_PROXY=socks5://127.0.0.1:49792 \
<your-command>
```

---

## 步骤 3：测试是否通了

测试 HuggingFace：

```bash
HTTPS_PROXY=http://127.0.0.1:49792 \
HTTP_PROXY=http://127.0.0.1:49792 \
ALL_PROXY=socks5://127.0.0.1:49792 \
curl -I --max-time 20 https://huggingface.co
```

如果看到：

- `HTTP/2 200`

说明代理通了。

---

## 已验证成功的事情

这套方法已经成功做过：

- 访问 HuggingFace 首页
- 下载 `princeton-nlp/SWE-bench_Lite`
- 补齐 Linux 侧 HF dataset cache

---

## 另一条路：Mac 先下载，再传给 hpc

如果不想让 Linux 直接走代理，也可以：

1. 在 Mac 上先下载数据
2. 再从 Mac 推送到 `hpc`

例子：

```bash
scp -r ~/Desktop/swebench_lite_export hpc:/Lishun/_archive/.local_env_bak/research/AgentOS/paper1/data/
```

这个方式已经成功用过。

适合：

- 数据量不大
- 只想传一份固定导出目录

---

## 当前已知可直接用的数据目录

Lite 数据本地目录：

```text
/Lishun/_archive/.local_env_bak/research/AgentOS/paper1/data/swebench_lite_export/
```

包含：

- `test.jsonl`
- `test.parquet`
- `dev.jsonl`
- `dev.parquet`
- `README.txt`

当前 `paper1/src/budgetflow/lite_tasks.py` 已优先读这个目录。

---

## 什么时候可以关掉 tunnel

当下面都不需要时再关：

- HF 下载
- GitHub 外网抓取
- 公开 calibration 数据下载
****
如果正在跑下载，千万别先关 main Mac 上那个 `ssh -R ...` 窗口。

---

## 一句话

如果 Linux 拉不到外网：

1. main Mac 开 `ssh -R 49792:127.0.0.1:49792 ...`
2. Linux 设置 `http_proxy / https_proxy / all_proxy`
3. 测试 `curl -I https://huggingface.co`
4. 再下载需要的数据
