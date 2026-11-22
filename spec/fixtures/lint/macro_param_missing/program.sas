/* PERIOD_END and N_ORIGINS are referenced but are not parameters. */
%macro Report(period_start=, N_ROWS= /* rows */, origins=, title=, unused=1);
  %put NOTE: &period_start &period_end &n_rows &origins &n_origins &title &unused;
%mend report;
