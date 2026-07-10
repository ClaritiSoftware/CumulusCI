from pathlib import Path

import click

_COMPLETIONS_DIR = Path(__file__).parent / "completions"


@click.group("completion", help="Generate shell completion scripts for cci")
def completion():
    pass


@completion.command(name="zsh")
def completion_zsh():
    """Output the zsh completion script for cci.

    \b
    Install (one-time setup):

      # Plain zsh - create a completions dir and add it to fpath in ~/.zshrc:
      mkdir -p ~/.zsh/completions
      cci completion zsh > ~/.zsh/completions/_cci
      # Add to ~/.zshrc:
      #   fpath=(~/.zsh/completions $fpath)
      #   autoload -Uz compinit && compinit

      # oh-my-zsh:
      mkdir -p ~/.oh-my-zsh/custom/completions
      cci completion zsh > ~/.oh-my-zsh/custom/completions/_cci

    Then restart your shell or run: autoload -Uz compinit && compinit
    """
    script = (_COMPLETIONS_DIR / "zsh" / "_cci").read_text(encoding="utf-8")
    click.echo(script, nl=False)


@completion.command(name="bash")
def completion_bash():
    """Output the bash completion script for cci.

    \b
    Install (one-time setup):

      # System-wide (requires sudo):
      cci completion bash | sudo tee /etc/bash_completion.d/cci > /dev/null

      # Per-user:
      cci completion bash >> ~/.bash_completion
    """
    # Use Click's built-in bash completion generator as the bash script
    click.echo(
        "# To generate a bash completion script, run:\n"
        "#   _CCI_COMPLETE=bash_source cci > ~/.bash_completion\n"
        "# or add this to your ~/.bashrc:\n"
        "#   eval \"$(_CCI_COMPLETE=bash_source cci)\"\n",
        err=True,
    )
    import subprocess
    import os

    env = os.environ.copy()
    env["_CCI_COMPLETE"] = "bash_source"
    result = subprocess.run(["cci"], env=env, capture_output=True, text=True)
    click.echo(result.stdout, nl=False)
