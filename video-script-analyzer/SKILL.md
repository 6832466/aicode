---
name: video-script-analyzer
description: >
  Analyze video files (anime drama, micro-drama, manga episodes) and generate
  detailed frame-by-frame storyboard scripts with camera movement annotations
  and per-shot duration markers. Supports single-video and batch processing.
  Uses Gemini API via OpenAI-compatible endpoint. Compression threshold: only
  compress videos exceeding 26MB. Skip already-analyzed episodes automatically.
  Keywords: 视频分析、分镜脚本、漫剧脚本、逐帧分析、镜头拆解、批量分析.
agent_created: true
tags:
  - video-analysis
  - storyboard
  - gemini
  - anime-drama
  - openai-compatible
  - batch-processing
disable: false
---

# Video Script Analyzer Skill

## Purpose

Analyze video files using Gemini API and generate detailed, frame-by-frame storyboard scripts with:
- Per-shot duration markers (`【时长X秒】`)
- Camera movement annotations (push-in, pull-back, pan, orbit, etc.)
- Dialogue with speaker emotions and delivery style
- Automatic skipping of already-analyzed episodes
- Video compression only when file exceeds 26MB (API payload limit)

## When to Use

- User provides video file(s) and asks for 分镜脚本 / storyboard / script
- User has multiple episodes to process in batch
- Keywords: 视频分析、分镜脚本、漫剧脚本、逐帧分析、镜头拆解、批量分析
- User says: "帮我分析这个视频"、"生成分镜脚本"、"这批视频全部分析"

## Prerequisites

- Gemini API endpoint (OpenAI-compatible): `https://www.geeknow.top/v1`
- API Key: `sk-MuEiwKWLDIpAX68VCmxcZV6cwuHHQR102Qke5P6xKFgYOmRT`
- Model: `gemini-3-pro-preview`
- Python environment with `openai` or use urllib (script handles both)
- For compression: `imageio-ffmpeg` (ffmpeg binary)
- Windows: Python output must use `Start-Process -RedirectStandardOutput` (GBK encoding issue)

## Workflow

### Single Video Analysis

1. Read `scripts/analyze_video.py` to understand the script structure
2. Confirm API config with user (or use defaults above)
3. Run via PowerShell `Start-Process` (never direct python call due to encoding):
   ```powershell
   $pyExe = "C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe"
   $script = "C:\Users\Administrator\.workbuddy\skills\video-script-analyzer\scripts\analyze_video.py"
   Start-Process -FilePath $pyExe -ArgumentList $script -Wait -NoNewWindow `
       -RedirectStandardOutput "analyze_out.txt" -RedirectStandardError "analyze_err.txt"
   ```
4. Check output log, deliver result file to user

### Batch Video Analysis (Recommended for Multiple Episodes)

1. Read `scripts/batch_analyze.py` — this is the primary script for batch processing
2. Configure before running:
   - `VIDEO_DIR`: directory containing all MP4 files
   - `API_KEY`, `API_BASE`, `MODEL`: API config
   - `COMPRESS_THRESHOLD_MB = 26`: only compress videos >26MB
   - `MAX_RETRIES = 5`: retry count for API calls
   - `MAX_TOKENS = 32000`: max response tokens
3. Run batch script:
   ```powershell
   $pyExe = "C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe"
   $batchScript = "C:\Users\Administrator\.workbuddy\skills\video-script-analyzer\scripts\batch_analyze.py"
   Start-Process -FilePath $pyExe -ArgumentList $batchScript `
       -RedirectStandardOutput "batch_log.txt" -RedirectStandardError "batch_err.txt"
   ```
4. Monitor progress: `Get-Content batch_log.txt -Tail 30`
5. Script auto-skips already analyzed episodes (checks for `*_分镜脚本.txt` files)

### Output Format (Strict)

Every output TXT must follow this exact format:

```
第X集：[集数标题]

[场景编号] [日/夜] [内/外景] [场景名称]
出场人物：[角色列表]

▲画面：【时长X秒】（画面描述）运镜方式描述。
台词/音效：角色名（情绪）：台词内容。

▲画面：【时长X秒】（画面描述）运镜方式描述。
台词/音效：角色名（情绪）：台词内容。
```

Rules:
- Every shot starts with `▲画面：【时长X秒】`
- Camera movement MUST be annotated in every shot
- Dialogue format: `角色名（情绪/动作）：台词`
- Inner monologue: `（os）`, voice-over: `（旁白）`
- All shot durations should sum to approximately the video's total duration
- Skip validation after analysis (user preference: save time)

### Video Compression (Automatic)

Triggered only when `file_size > COMPRESS_THRESHOLD_MB` (default 26MB):
1. Script auto-installs `imageio-ffmpeg` if ffmpeg not found
2. Uses ffmpeg `libx264` CRF mode (better than bitrate mode)
3. Progressive compression attempts: half-res → 3/8-res → quarter-res
4. Removes audio track to save space (`-an`)
5. Temp files auto-cleaned after upload

### Error Handling

- API timeout/SSL errors: auto-retry with exponential backoff (20s, 40s, 60s, 80s, 100s)
- Compression failure: use original file (warn user)
- Missing ffmpeg: `pip install imageio-ffmpeg` automatically

## Bundled Resources

| File | Purpose |
|------|---------|
| `scripts/analyze_video.py` | Single video analysis script |
| `scripts/batch_analyze.py` | Batch analysis with auto-skip and compression |
| `references/prompt_template.md` | Default prompt template (customize per user need) |
| `references/api_templates.json` | API request templates for different providers |

## Customization

- To change output language: edit prompt in `references/prompt_template.md`
- To change compression threshold: edit `COMPRESS_THRESHOLD_MB` in `batch_analyze.py`
- To add validation step: uncomment validation code in batch script
- To change API endpoint: update `API_BASE` and `API_KEY` in scripts

## Known Limitations

- Python `print()` fails on Windows with GBK encoding — always use `Start-Process -RedirectStandardOutput`
- Very large videos (>100MB) may need manual splitting before analysis
- Gemini API has ~26MB base64 payload limit — compression handles this automatically
