"""Rich text configuration."""

import click
import rich.console
import rich.theme
import rich.traceback


# theme with custom styles
THEME = rich.theme.Theme({
	"validation.issue.fatal": "bold red1 on bright_white",
	#"validation.issue.fatal": "bold red1",
	"validation.issue.error": "bold red1",
	"validation.issue.warning": "dark_orange",
	"validation.issue.notice": "cyan",

	"validation.target": "spring_green3",
	"validation.location": "deep_pink3 underline",

	"challenge.difficulty.undefined": "grey50",
	"challenge.difficulty.easy": "spring_green3",
	"challenge.difficulty.medium": "yellow3",
	"challenge.difficulty.hard": "red1",
}, inherit=True)


# shared global console
CONSOLE = rich.console.Console(
	theme = THEME,
	# for exporting console output
	record = True,
)


# use rich for pretty exceptions
rich.traceback.install(suppress=[click])
