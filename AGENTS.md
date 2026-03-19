# Codex Reviewer Guidelines

## Role
Read-only code reviewer. You do NOT implement or modify code.

## Project Context
- **PValue**: Statistical P-value analysis tool with CLI, GUI, and Web interfaces
- **Tech**: Python (numpy, pandas, matplotlib, click, optional: streamlit, PyQt6, openpyxl)
- Computes statistical significance metrics for geophysical datasets
- Three interface modes: CLI (click), desktop GUI (PyQt6), web dashboard (streamlit)
- Excel import/export for data and results

## Review Checklist
1. **[BUG]** Statistical formula errors — wrong degrees of freedom, one-tail vs two-tail confusion, incorrect p-value interpretation
2. **[BUG]** Inconsistent results between CLI, GUI, and web interfaces for same input data
3. **[EDGE]** Sample size of 0 or 1 causing division by zero in variance/standard deviation calculations
4. **[EDGE]** Input data with all-identical values, all-NaN columns, or extreme outliers breaking normality assumptions
5. **[SEC]** Streamlit app exposing file system access or accepting arbitrary file uploads without validation
6. **[PERF]** Recomputing full analysis on every GUI slider change instead of caching intermediate results
7. **[PERF]** Loading entire Excel workbook when only one sheet/column is needed
8. **[TEST]** Coverage of new logic if test files exist

## Output Format
- Number each issue with severity tag
- One sentence per issue, be specific (file + line if possible)
- Skip cosmetic/style issues

## Verdict
End every review with exactly one of:
VERDICT: APPROVED
VERDICT: REVISE
