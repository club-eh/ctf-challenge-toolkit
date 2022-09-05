# isort: skip_file

# handle toml import here for other modules
import sys
if sys.version_info >= (3, 11):
	# Python >= 3.11 (stdlib module)
	import tomllib
else:
	# Python <= 3.10 (third-party dependency)
	import tomli as tomllib


# import CLI commands
from . import commands
