# CTF Challenge ToolKit

A CLI tool for automating challenge management and deployment.


## Installation

Use `pip` to install the latest development version (also handles updating):
```shell
pip install --force-reinstall 'git+https://git.sb418.net/sudoBash418/ctf-challenge-toolkit.git'
```


## Usage

### Validation

To validate a challenge (or multiple challenges), use the `validate` subcommand:

```shell
cctk validate example     # validates the `example` challenge
cctk validate             # validates all challenges in the repo
cctk validate -s example  # validates all challenges in the repo, skipping the `example` challenge
```

If any issues are found, they will be displayed and a table summarizing the issues will be printed at the end.  
Otherwise, a success message will state that no issues have occurred.

You can use `-R/--repo`  to specify the location of the challenge repository (it defaults to the current directory).  
Make sure you pass the option *before* the subcommand (`cctk -R [...] validate` instead of `cctk validate -R [...]`), or the argument parser will fail.
