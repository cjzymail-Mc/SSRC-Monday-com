"""Test-only access to the mounted legacy board used by older browser suites."""


def reveal_legacy_board(page, ready_selector=".task-row"):
    """Wait for app startup, then expose the legacy board only in this test page."""
    page.wait_for_function(
        """() => {
          if (typeof state === 'undefined' || !state.current_user) return false;
          const identity = document.querySelector('#currentUser > span:not(.avatar)');
          const loadState = document.querySelector('#loadState');
          if (!identity?.textContent.trim() || loadState?.textContent !== '刚刚同步') return false;
          const canUseTimeline = Boolean(state.capabilities?.write || state.capabilities?.admin);
          return !canUseTimeline || !document.querySelector('#timelineView')?.hidden;
        }"""
    )
    page.evaluate(
        """() => {
          const board = document.querySelector('#boardWorkspace');
          const timeline = document.querySelector('#timelineView');
          if (timeline) timeline.hidden = true;
          if (board) {
            board.hidden = false;
            board.removeAttribute('aria-hidden');
            board.style.setProperty('display', 'block', 'important');
          }
        }"""
    )
    page.locator(ready_selector).first.wait_for()


def reload_legacy_board(page, ready_selector=".task-row"):
    page.reload()
    reveal_legacy_board(page, ready_selector)


def goto_legacy_board(page, url, ready_selector=".task-row"):
    page.goto(url)
    reveal_legacy_board(page, ready_selector)
