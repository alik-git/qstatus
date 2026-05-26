"""Opt-in shell reminders for quick-status."""

_BASH_REMINDERS = r"""# quick-status reminders: opt-in interactive shell integration.
__quick_status_reminders_init() {
    case $- in
        *i*) ;;
        *) return 0 ;;
    esac

    __quick_status_reminder_maybe_print() {
        local rc="$1"
        shift || true
        [ "$rc" = "0" ] || return 0
        [ "${QUICK_STATUS_REMINDERS:-1}" != "0" ] || return 0
        [ -t 2 ] || return 0

        local tool="$1"
        shift || true
        local suggestion=""

        case "$tool" in
            git)
                case "$*" in
                    "status")
                        suggestion="quick-status repo --plain"
                        ;;
                    "status --short")
                        suggestion="quick-status repo --plain"
                        ;;
                    "status --short --branch")
                        suggestion="quick-status repo --plain"
                        ;;
                    "status --porcelain")
                        suggestion="quick-status repo --plain"
                        ;;
                    "branch")
                        suggestion="quick-status repo --plain"
                        ;;
                    "branch --show-current")
                        suggestion="quick-status repo --plain"
                        ;;
                    "rev-parse --show-toplevel")
                        suggestion="quick-status repo --plain"
                        ;;
                    "rev-parse --show-toplevel --git-dir")
                        suggestion="quick-status repo --plain"
                        ;;
                    "remote -v")
                        suggestion="quick-status repo --plain"
                        ;;
                    "stash list")
                        suggestion="quick-status repo --plain"
                        ;;
                    "submodule status")
                        suggestion="quick-status repo --plain"
                        ;;
                    "worktree list")
                        suggestion="quick-status repo --plain --worktrees"
                        ;;
                    "worktree list --porcelain")
                        suggestion="quick-status repo --plain --worktrees"
                        ;;
                    "tag --list")
                        suggestion="quick-status repo --plain --github"
                        ;;
                    "tag -l")
                        suggestion="quick-status repo --plain --github"
                        ;;
                    "log --left-right --cherry-pick"*)
                        suggestion="quick-status repo --plain --github"
                        ;;
                esac
                ;;
            gh)
                case "$*" in
                    "pr status")
                        suggestion="quick-status repo --plain --github"
                        ;;
                    pr\ view*)
                        suggestion="quick-status repo --plain --github"
                        ;;
                    pr\ checks*)
                        suggestion="quick-status repo --plain --github"
                        ;;
                    "run list")
                        suggestion="quick-status repo --plain --github"
                        ;;
                    run\ view*)
                        suggestion="quick-status repo --plain --github"
                        ;;
                    "release list")
                        suggestion="quick-status repo --plain --github"
                        ;;
                    release\ view*)
                        suggestion="quick-status repo --plain --github"
                        ;;
                esac
                ;;
            which)
                case "$*" in
                    "python")
                        suggestion="quick-status env --plain --show-tools"
                        ;;
                    "python3")
                        suggestion="quick-status env --plain --show-tools"
                        ;;
                    "pip")
                        suggestion="quick-status env --plain --show-tools"
                        ;;
                    "pip3")
                        suggestion="quick-status env --plain --show-tools"
                        ;;
                    "conda")
                        suggestion="quick-status env --plain --show-tools"
                        ;;
                    "uv")
                        suggestion="quick-status env --plain --show-tools"
                        ;;
                    "devpy")
                        suggestion="quick-status env --plain --show-tools"
                        ;;
                esac
                ;;
            python|python3|pip|pip3)
                case "$*" in
                    "--version")
                        suggestion="quick-status env --plain --show-tools"
                        ;;
                esac
                ;;
            conda)
                case "$*" in
                    "info")
                        suggestion="quick-status env --plain --show-tools"
                        ;;
                    "env list")
                        suggestion="quick-status env --plain --show-tools"
                        ;;
                    "config --show auto_activate_base")
                        suggestion="quick-status env --plain --show-tools"
                        ;;
                esac
                ;;
            uv)
                case "$*" in
                    "python list")
                        suggestion="quick-status env --plain --show-tools"
                        ;;
                    "python dir")
                        suggestion="quick-status env --plain --show-tools"
                        ;;
                    "tool list")
                        suggestion="quick-status env --plain --show-tools"
                        ;;
                esac
                ;;
            devpy)
                case "$*" in
                    "info")
                        suggestion="quick-status env --plain --show-tools"
                        ;;
                esac
                ;;
        esac

        [ -n "$suggestion" ] || return 0
        printf '%s\n' \
            "Consider using quick-status next time to save time! Try: $suggestion" >&2
    }

    __quick_status_reminders_can_wrap() {
        case "$(type -t "$1" 2>/dev/null)" in
            file|builtin) return 0 ;;
            *) return 1 ;;
        esac
    }

    if __quick_status_reminders_can_wrap git; then
        git() {
            command git "$@"
            local rc=$?
            __quick_status_reminder_maybe_print "$rc" git "$@"
            return "$rc"
        }
    fi

    if __quick_status_reminders_can_wrap gh; then
        gh() {
            command gh "$@"
            local rc=$?
            __quick_status_reminder_maybe_print "$rc" gh "$@"
            return "$rc"
        }
    fi

    if __quick_status_reminders_can_wrap python; then
        python() {
            command python "$@"
            local rc=$?
            __quick_status_reminder_maybe_print "$rc" python "$@"
            return "$rc"
        }
    fi

    if __quick_status_reminders_can_wrap python3; then
        python3() {
            command python3 "$@"
            local rc=$?
            __quick_status_reminder_maybe_print "$rc" python3 "$@"
            return "$rc"
        }
    fi

    if __quick_status_reminders_can_wrap pip; then
        pip() {
            command pip "$@"
            local rc=$?
            __quick_status_reminder_maybe_print "$rc" pip "$@"
            return "$rc"
        }
    fi

    if __quick_status_reminders_can_wrap pip3; then
        pip3() {
            command pip3 "$@"
            local rc=$?
            __quick_status_reminder_maybe_print "$rc" pip3 "$@"
            return "$rc"
        }
    fi

    if __quick_status_reminders_can_wrap conda; then
        conda() {
            command conda "$@"
            local rc=$?
            __quick_status_reminder_maybe_print "$rc" conda "$@"
            return "$rc"
        }
    fi

    if __quick_status_reminders_can_wrap uv; then
        uv() {
            command uv "$@"
            local rc=$?
            __quick_status_reminder_maybe_print "$rc" uv "$@"
            return "$rc"
        }
    fi

    if __quick_status_reminders_can_wrap devpy; then
        devpy() {
            command devpy "$@"
            local rc=$?
            __quick_status_reminder_maybe_print "$rc" devpy "$@"
            return "$rc"
        }
    fi

    if __quick_status_reminders_can_wrap which; then
        which() {
            command which "$@"
            local rc=$?
            __quick_status_reminder_maybe_print "$rc" which "$@"
            return "$rc"
        }
    fi
}
__quick_status_reminders_init
unset -f __quick_status_reminders_init __quick_status_reminders_can_wrap
"""


def render_reminders_init(shell: str) -> str:
    """Return opt-in shell integration source for quick-status reminders."""
    if shell != "bash":
        msg = f"unsupported reminders shell: {shell}"
        raise ValueError(msg)
    return _BASH_REMINDERS
