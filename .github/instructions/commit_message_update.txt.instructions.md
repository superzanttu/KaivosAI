---
applyTo: '**'
---
Always update `commit_message.txt` immediately after making code changes. Append a single new entry describing the latest change(s) to the end of the file; do not remove or overwrite previous entries. The file is treated as an append-only changelog used by the automatic commit helper.
Always update VERSION constant immediately after making code changes. Increment the version according to the nature of the changes made (patch, minor, major) following semantic versioning principles.
Always create `flag_new_version.lck` file immediately after updating VERSION constant. This signals the running game to restart and load the new code. The flag file should be empty and will be automatically deleted by the game after restart.