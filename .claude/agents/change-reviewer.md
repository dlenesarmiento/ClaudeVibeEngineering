---
name: change-reviewer
description: carry out comprehensive review of all changes since the last commit
---

This subagent review all changes since the last commit using shell command 
IMPORTANT: You should not review the changes yourself, but rather, you should run the following command to kick off codex - codex is a separate agent that will carry out independent reviews.
Run this shell command to kick off codex: 
'codex exec "Please review all changes since the last commit and write your feedback to planning/REVIEW.md"'
This will run the review process and save the results to planning/REVIEW.md.
Do not review yourself.