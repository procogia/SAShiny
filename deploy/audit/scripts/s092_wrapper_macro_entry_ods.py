"""Audit 92: wrapper_macro_entry_ods. Category: wrapper-fixtures."""
from client import *

body = {'fixture': 'wrapper/macro_entry_ods', 'values': {'arm': 'Drug A'}, 'uploads': {'adsl': True}, 'today': '2026-11-11', 'run_id': 'fixture'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'wrapper', body)
        assert got['main'] == '/* SAShiny 1 wrapper: generated, do not edit */\n%put NOTE: SASHINY-BEGIN run=fixture;\n%let syscc = 0;\ndata _null_;\n  call symputx(\'ADSL_DS\', \'WORK.ADSL\', \'G\');\n  call symputx(\'ARM\', \'\'\'Drug A\'\'\', \'G\');\nrun;\nods rtf(id=rtf_a) file="%sysfunc(pathname(work))/sashiny_rtf_a.rtf";\nods pdf(id=pdf_a) file="%sysfunc(pathname(work))/sashiny_pdf_a.pdf";\nods rtf(id=rtf_b) file="%sysfunc(pathname(work))/sashiny_rtf_b.rtf";\n%put NOTE: SASHINY-BEGIN-PROGRAM;\n%macro ae_table(adsl_ds=, arm=);\n  %put NOTE: &adsl_ds &arm;\n%mend ae_table;\n%ae_table(ADSL_DS=%bquote(&ADSL_DS), ARM=%bquote(&ARM));\n%put NOTE: SASHINY-END-PROGRAM;\nods rtf(id=rtf_a) close;\nods pdf(id=pdf_a) close;\nods rtf(id=rtf_b) close;\n%put NOTE: SASHINY-END run=fixture syscc=&syscc;\n', (language, got)
        assert not got['issues']
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
