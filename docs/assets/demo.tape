# vhs docs/assets/demo.tape
# Renders docs/assets/demo.gif. Run from the repo root: vhs docs/assets/demo.tape
# Requires: vhs (https://github.com/charmbracelet/vhs), uv, examples/*.epub present.

Output docs/assets/demo.gif

Set FontSize 16
Set Width 1200
Set Height 650
Set Theme "Dracula"
Set Shell "bash"

Hide
Type "export LIB_HOME=$(mktemp -d)"
Enter
Type "alias lib='uv run lib'"
Enter
Type "lib --help >/dev/null 2>&1"
Enter
Sleep 2s
Type "clear"
Enter
Show

Type "lib ingest examples/*.epub"
Enter
Sleep 4s

Type "lib list"
Enter
Sleep 3s

Type `lib find "curiouser"`
Enter
Sleep 3.5s

Hide
Type `export ALICE_ID=$(python3 -c "import json; d=json.load(open('$LIB_HOME/index.json')); print([b['id'] for b in d['books'] if 'alice' in b['id'].lower()][0])")`
Enter
Type "clear"
Enter
Show

Type `lib get "$ALICE_ID" --budget 3000`
Enter
Sleep 5s
