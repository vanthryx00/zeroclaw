# Tham khảo lệnh MegaZero

Dựa trên CLI hiện tại (`mega-zero --help`).

Xác minh lần cuối: **2026-02-20**.

## Lệnh cấp cao nhất

| Lệnh | Mục đích |
|---|---|
| `onboard` | Khởi tạo workspace/config nhanh hoặc tương tác |
| `agent` | Chạy chat tương tác hoặc chế độ gửi tin nhắn đơn |
| `gateway` | Khởi động gateway webhook và HTTP WhatsApp |
| `daemon` | Khởi động runtime có giám sát (gateway + channels + heartbeat/scheduler tùy chọn) |
| `service` | Quản lý vòng đời dịch vụ cấp hệ điều hành |
| `doctor` | Chạy chẩn đoán và kiểm tra trạng thái |
| `status` | Hiển thị cấu hình và tóm tắt hệ thống |
| `cron` | Quản lý tác vụ định kỳ |
| `models` | Làm mới danh mục model của provider |
| `providers` | Liệt kê ID provider, bí danh và provider đang dùng |
| `channel` | Quản lý kênh và kiểm tra sức khỏe kênh |
| `integrations` | Kiểm tra chi tiết tích hợp |
| `skills` | Liệt kê/cài đặt/gỡ bỏ skills |
| `migrate` | Nhập dữ liệu từ runtime khác (hiện hỗ trợ OpenClaw) |
| `config` | Xuất schema cấu hình dạng máy đọc được |
| `completions` | Tạo script tự hoàn thành cho shell ra stdout |
| `hardware` | Phát hiện và kiểm tra phần cứng USB |
| `peripheral` | Cấu hình và nạp firmware thiết bị ngoại vi |

## Nhóm lệnh

### `onboard`

- `mega-zero onboard`
- `mega-zero onboard --interactive`
- `mega-zero onboard --channels-only`
- `mega-zero onboard --api-key <KEY> --provider <ID> --memory <sqlite|lucid|markdown|none>`
- `mega-zero onboard --api-key <KEY> --provider <ID> --model <MODEL_ID> --memory <sqlite|lucid|markdown|none>`

### `agent`

- `mega-zero agent`
- `mega-zero agent -m "Hello"`
- `mega-zero agent --provider <ID> --model <MODEL> --temperature <0.0-2.0>`
- `mega-zero agent --peripheral <board:path>`

### `gateway` / `daemon`

- `mega-zero gateway [--host <HOST>] [--port <PORT>]`
- `mega-zero daemon [--host <HOST>] [--port <PORT>]`

### `service`

- `mega-zero service install`
- `mega-zero service start`
- `mega-zero service stop`
- `mega-zero service restart`
- `mega-zero service status`
- `mega-zero service uninstall`

### `cron`

- `mega-zero cron list`
- `mega-zero cron add <expr> [--tz <IANA_TZ>] <command>`
- `mega-zero cron add-at <rfc3339_timestamp> <command>`
- `mega-zero cron add-every <every_ms> <command>`
- `mega-zero cron once <delay> <command>`
- `mega-zero cron remove <id>`
- `mega-zero cron pause <id>`
- `mega-zero cron resume <id>`

### `models`

- `mega-zero models refresh`
- `mega-zero models refresh --provider <ID>`
- `mega-zero models refresh --force`

`models refresh` hiện hỗ trợ làm mới danh mục trực tiếp cho các provider: `openrouter`, `openai`, `anthropic`, `groq`, `mistral`, `deepseek`, `xai`, `together-ai`, `gemini`, `ollama`, `astrai`, `venice`, `fireworks`, `cohere`, `moonshot`, `glm`, `zai`, `qwen` và `nvidia`.

### `channel`

- `mega-zero channel list`
- `mega-zero channel start`
- `mega-zero channel doctor`
- `mega-zero channel bind-telegram <IDENTITY>`
- `mega-zero channel add <type> <json>`
- `mega-zero channel remove <name>`

Lệnh trong chat khi runtime đang chạy (Telegram/Discord):

- `/models`
- `/models <provider>`
- `/model`
- `/model <model-id>`

Channel runtime cũng theo dõi `config.toml` và tự động áp dụng thay đổi cho:
- `default_provider`
- `default_model`
- `default_temperature`
- `api_key` / `api_url` (cho provider mặc định)
- `reliability.*` cài đặt retry của provider

`add/remove` hiện chuyển hướng về thiết lập có hướng dẫn / cấu hình thủ công (chưa hỗ trợ đầy đủ mutator khai báo).

### `integrations`

- `mega-zero integrations info <name>`

### `skills`

- `mega-zero skills list`
- `mega-zero skills install <source>`
- `mega-zero skills remove <name>`

`<source>` chấp nhận git remote (`https://...`, `http://...`, `ssh://...` và `git@host:owner/repo.git`) hoặc đường dẫn cục bộ.

Skill manifest (`SKILL.toml`) hỗ trợ `prompts` và `[[tools]]`; cả hai được đưa vào system prompt của agent khi chạy, giúp model có thể tuân theo hướng dẫn skill mà không cần đọc thủ công.

### `migrate`

- `mega-zero migrate openclaw [--source <path>] [--dry-run]`

### `config`

- `mega-zero config schema`

`config schema` xuất JSON Schema (draft 2020-12) cho toàn bộ hợp đồng `config.toml` ra stdout.

### `completions`

- `mega-zero completions bash`
- `mega-zero completions fish`
- `mega-zero completions zsh`
- `mega-zero completions powershell`
- `mega-zero completions elvish`

`completions` chỉ xuất ra stdout để script có thể được source trực tiếp mà không bị lẫn log/cảnh báo.

### `hardware`

- `mega-zero hardware discover`
- `mega-zero hardware introspect <path>`
- `mega-zero hardware info [--chip <chip_name>]`

### `peripheral`

- `mega-zero peripheral list`
- `mega-zero peripheral add <board> <path>`
- `mega-zero peripheral flash [--port <serial_port>]`
- `mega-zero peripheral setup-uno-q [--host <ip_or_host>]`
- `mega-zero peripheral flash-nucleo`

## Kiểm tra nhanh

Để xác minh nhanh tài liệu với binary hiện tại:

```bash
mega-zero --help
mega-zero <command> --help
```
