/* SAShiny 1 wrapper: generated, do not edit */
%put NOTE: SASHINY-BEGIN run=fixture;
%let syscc = 0;
data _null_;
  call symputx('ARMS', '''Placebo'', ''Drug A''', 'G');
run;
%put NOTE: SASHINY-BEGIN-PROGRAM;
%macro arms_table(arms=);
  %put NOTE: &arms;
%mend arms_table;
%arms_table(ARMS=%bquote(&ARMS));
%put NOTE: SASHINY-END-PROGRAM;
%put NOTE: SASHINY-END run=fixture syscc=&syscc;
