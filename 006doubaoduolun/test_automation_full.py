"""
Full automation test: send 2 messages using the new Playwright-based automation.py
"""
import asyncio
import time
from models import AppConfig, SendMessage, ChatMode, SwitchStrategy
from automation import DoubaoAutomation


def test_full_automation():
    config = AppConfig()
    config.send_interval = 3  # short interval for testing
    config.expert_rounds = 1  # first msg expert, second think
    config.switch_strategy = SwitchStrategy.FIXED_ROUNDS

    engine = DoubaoAutomation(config)

    # connect to Chrome
    print("Connecting to Chrome...")
    if not engine.start_browser():
        print("FAIL: Could not connect to Chrome")
        return

    print("Connected!")

    # set up callbacks
    log_lines = []
    replies = []
    statuses = []

    def on_log(text):
        log_lines.append(text)
        print(f"  LOG: {text}")

    def on_status(msg_id, status):
        statuses.append((msg_id, status))
        print(f"  STATUS: msg#{msg_id} -> {status.value}")

    def on_reply(reply):
        replies.append(reply)
        print(f"  REPLY #{reply.id}: {reply.content[:80]!r} ({reply.elapsed_seconds}s, {reply.mode.value})")

    def on_mode(mode):
        print(f"  MODE: switched to {mode.value}")

    engine.on_log = on_log
    engine.on_status_change = on_status
    engine.on_reply_received = on_reply
    engine.on_mode_changed = on_mode

    # prepare messages
    messages = [
        SendMessage(id=1, content="请回复「第一条收到」五个字，不要说其他内容。"),
        SendMessage(id=2, content="请回复「第二条收到」五个字，不要说其他内容。"),
    ]

    print(f"\nSending {len(messages)} messages...")
    t_start = time.time()
    engine.run(messages, start_index=0)
    elapsed = time.time() - t_start

    print(f"\n=== RESULTS (total {elapsed:.1f}s) ===")
    print(f"Replies received: {len(replies)}")
    for r in replies:
        print(f"  Reply #{r.id} (send #{r.send_id}): {r.content!r} [{r.elapsed_seconds}s, {r.mode.value}]")

    print(f"\nStatus history:")
    for msg_id, status in statuses:
        print(f"  msg#{msg_id}: {status.value}")

    # assertions
    assert len(replies) == 2, f"Expected 2 replies, got {len(replies)}"
    assert messages[0].status.value == "已发送"
    assert messages[1].status.value == "已发送"
    print("\nALL ASSERTIONS PASSED")

    engine.close_browser()


test_full_automation()
