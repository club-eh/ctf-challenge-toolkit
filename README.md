# CTF Challenge ToolKit

A CLI tool for automating challenge management and deployment.

Currently only supports CTFd.


## Installation

Use `pip` to install the latest development version (also handles updating):
```shell
pip install --force-reinstall 'git+https://git.sb418.net/sudoBash418/ctf-challenge-toolkit.git'
```

Or use [`pipx`](https://pypa.github.io/pipx/):
```shell
pipx install 'git+https://git.sb418.net/sudoBash418/ctf-challenge-toolkit.git'
```


## Usage

#### Tips

You can use `-R/--repo`  to specify the location of the challenge repository (it defaults to the current directory).  
Make sure you pass the option *before* the subcommand (`cctk -R [...] validate` instead of `cctk validate -R [...]`), or the argument parser will fail.

Help text is available by passing `--help` to `cctk` or any of its subcommands.

### Validation

To validate a challenge (or multiple challenges), use the `validate` subcommand:

```shell
cctk validate example     # validates the `example` challenge
cctk validate             # validates all challenges in the repo
cctk validate -s example  # validates all challenges in the repo, skipping the `example` challenge
```

If any issues are found, they will be displayed and a table summarizing the issues will be printed at the end.  
Otherwise, a success message will state that no issues have occurred.

### Deployment

To deploy a challenge (or multiple challenges), use the `deploy` subcommand:
```shell
cctk deploy example     # validates + deploys the `example` challenge
cctk deploy             # validates + deploys all challenges in the repo
cctk deploy -s example  # validates + deploys all challenges in the repo, skipping the `example` challenge
```

Validation is still performed before any changes are made, as with the `validate` subcommand.  
If validation succeeds, the deployment process will begin by reading the current state of the CTFd instance, to determine what changes need to be made.  
Once this process is finished, a table summarizing the pending changes will be displayed, with a confirmation prompt before any changes are actually made.  
This allows you to carefully review the pending changes before any action is taken, so you can catch errors before they cause irrevocable damage to the CTFd instance.

There are a few more options for specifying how to interact with the CTFd instance: `-u/--url` and `-t/--token`.  
If these parameters are not provided through either CLI arguments, environment variables, or the challenge repo config, you will be interactively prompted for the missing information.
