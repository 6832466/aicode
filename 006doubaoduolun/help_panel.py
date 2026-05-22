from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QLabel
from PySide6.QtCore import Qt
from qfluentwidgets import isDarkTheme

HELP_BODY = """
<h2>🚀 快速开始</h2>
<div class="tip">
  <b>前提：</b>需要用调试模式启动 Chrome，让工具能连接到你已登录的豆包页面。
</div>

<h3>第一步：连接浏览器</h3>
点击 <b>连接浏览器</b> 按钮，软件会自动关闭现有 Chrome、以调试模式重新启动并打开豆包页面。
<br>如果自动启动失败，也可以手动在命令行执行：
<br><br>
<code>chrome.exe --remote-debugging-port=9222 --user-data-dir=C:\\Temp\\chrome-doubao</code>
<br><br>
启动后在浏览器中打开 <code>https://www.doubao.com/chat/</code> 并登录账号。

<h3>第二步：新建对话</h3>
点击 <b>新建对话</b> 按钮，软件会跳转到豆包新对话页面。

<h3>第三步：添加消息</h3>
点击 <b>添加消息</b> 逐条输入，或点击 <b>导入文件</b> 批量导入。

<h3>第四步：开始执行</h3>
点击 <b>开始执行</b>，软件会自动按顺序发送消息并收集回复。

<hr>

<h2>📋 消息队列操作</h2>
<ul>
  <li><b>添加消息</b>：弹窗输入消息内容，可指定该条消息强制使用的模式（默认跟随全局策略）</li>
  <li><b>导入文件</b>：支持 <code>.txt</code>（每行一条）、<code>.csv</code>（第一列为内容）、<code>.xlsx</code>，也可直接粘贴多行文本</li>
  <li><b>双击行</b>：查看消息完整内容</li>
  <li><b>编辑 / 删除 / 上移 / 下移</b>：通过每行右侧操作按钮完成</li>
  <li><b>从序号继续</b>：输入序号后点击"继续执行"，从指定条目重新开始（适合中途失败后续跑）</li>
</ul>

<h2>💬 模式切换策略</h2>
顶部配置栏的格式为：<b>前 N 轮使用 [模式A]，之后切换为 [模式B]</b>
<ul>
  <li>模式可选：<b>专家模式</b>、<b>思考模式</b>、<b>快速模式</b></li>
  <li>N 填 0 表示全程使用模式B；N 填一个很大的数表示全程使用模式A</li>
  <li>例如：前 3 轮专家模式，之后思考模式</li>
</ul>
<div class="tip">
  每条消息也可以在添加时单独指定模式，优先级高于全局策略。
</div>

<h2>⚙️ 参数说明</h2>
<ul>
  <li><b>前 N 轮</b>：前多少轮使用第一个模式，超过后切换为第二个模式</li>
  <li><b>发送间隔（秒）</b>：每条消息收到回复后，等待多少秒再发下一条。建议 3~10 秒</li>
  <li><b>系统提示词</b>：新建对话后自动发送一条指令，用于设定豆包的角色或行为规范</li>
</ul>

<h2>📤 导出回复</h2>
在"豆包回复记录"面板点击 <b>导出回复</b>，支持两种格式：
<ul>
  <li><b>.txt</b>：序号 + 回复内容，每条一行，格式为 <code>1. 回复内容...</code>（多行内容自动合并为一行）</li>
  <li><b>.xlsx</b>：Excel 表格，包含发送序号、发送消息内容、发送模式、回复序号、回复内容，回复内容列自动换行</li>
</ul>

<h2>🔍 实时日志</h2>
切换到 <b>运行日志</b> 页面可查看详细的执行过程：
<ul>
  <li>按级别过滤：DEBUG / INFO / WARNING / ERROR</li>
  <li>关键词搜索：实时过滤日志内容</li>
  <li><b>复制全部</b>：一键复制当前过滤结果，方便粘贴给开发者排查问题</li>
  <li>ERROR 级别日志会高亮显示红色背景，便于快速定位异常</li>
</ul>

<h2>⚠️ 常见问题</h2>

<h3>连接 Chrome 失败</h3>
<div class="warn">
  确保 Chrome 是用 <code>--remote-debugging-port=9222</code> 参数启动的，且没有其他 Chrome 进程占用该端口。
  可在浏览器地址栏访问 <code>http://localhost:9222</code> 验证是否正常。
</div>

<h3>消息发送成功但没有收到回复</h3>
<div class="warn">
  豆包页面可能正在生成中，默认等待超时为 120 秒。如果网络较慢或回复很长，可适当增大"发送间隔"。
  也可切换到"运行日志"查看具体报错。
</div>

<h3>模式切换失败</h3>
<div class="warn">
  豆包页面需要处于对话输入状态才能切换模式。如果切换失败，工具会跳过切换继续发送，
  日志中会显示"模式切换失败，继续发送"。
</div>

<h3>中途失败想从某条继续</h3>
<div class="tip">
  在"从序号继续"输入框填入要重新开始的消息序号，点击"继续执行"即可。
  已成功的消息不会重复发送。
</div>
"""

_CSS_LIGHT = """
<style>
  body  { font-family: "Microsoft YaHei", sans-serif; font-size: 15px; line-height: 1.9; color: #1a1a1a; }
  h2    { color: #0078d4; margin-top: 24px; margin-bottom: 6px; font-size: 18px;
          border-bottom: 1px solid #d0d0d0; padding-bottom: 4px; }
  h3    { color: #005a9e; margin-top: 16px; margin-bottom: 4px; font-size: 16px; }
  code  { background: #f0f0f0; color: #c7254e; padding: 1px 6px; border-radius: 3px;
          font-family: Consolas, monospace; font-size: 14px; }
  ul    { margin: 4px 0 4px 20px; }
  li    { margin-bottom: 5px; }
  hr    { border: none; border-top: 1px solid #d0d0d0; margin: 16px 0; }
  .tip  { background: #e8f5e9; border-left: 3px solid #43a047; padding: 8px 12px;
          margin: 8px 0; border-radius: 0 4px 4px 0; color: #1b5e20; }
  .warn { background: #fff8e1; border-left: 3px solid #fb8c00; padding: 8px 12px;
          margin: 8px 0; border-radius: 0 4px 4px 0; color: #4e3400; }
</style>
"""

_CSS_DARK = """
<style>
  body  { font-family: "Microsoft YaHei", sans-serif; font-size: 15px; line-height: 1.9; color: #e8e8e8; }
  h2    { color: #4fc3f7; margin-top: 24px; margin-bottom: 6px; font-size: 18px;
          border-bottom: 1px solid #444; padding-bottom: 4px; }
  h3    { color: #81d4fa; margin-top: 16px; margin-bottom: 4px; font-size: 16px; }
  code  { background: #2a2a2a; color: #80cbc4; padding: 1px 6px; border-radius: 3px;
          font-family: Consolas, monospace; font-size: 14px; }
  ul    { margin: 4px 0 4px 20px; }
  li    { margin-bottom: 5px; }
  hr    { border: none; border-top: 1px solid #444; margin: 16px 0; }
  .tip  { background: #1a2e1a; border-left: 3px solid #4caf50; padding: 8px 12px;
          margin: 8px 0; border-radius: 0 4px 4px 0; }
  .warn { background: #2e2000; border-left: 3px solid #ffb74d; padding: 8px 12px;
          margin: 8px 0; border-radius: 0 4px 4px 0; }
</style>
"""


class HelpPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 16, 24, 24)
        content_layout.setSpacing(0)

        self._label = QLabel()
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self._label.setWordWrap(True)
        self._label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._label.setOpenExternalLinks(True)
        content_layout.addWidget(self._label)
        content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)

        self._refresh_theme()

    def _refresh_theme(self):
        css = _CSS_DARK if isDarkTheme() else _CSS_LIGHT
        self._label.setText(css + HELP_BODY)

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_theme()
