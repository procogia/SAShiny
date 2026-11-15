%macro report(Region=, top_n=);
  %let region = %upcase(&region);
  %let TOP_N = %sysfunc(max(&top_n, 1));
  %let label = Top &top_n in &region;
  %put NOTE: &label;
%mend report;
%let top_n = 10;
