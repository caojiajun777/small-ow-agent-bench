# Worker operations policy

The production retry plugin selected by hooks.json allows at most **five attempts total**, including the first attempt. Retry outcomes are per job; a successful job stops immediately. Changing plugin selection is not part of this maintenance issue.
