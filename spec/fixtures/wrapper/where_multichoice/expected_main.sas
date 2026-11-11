/* SAShiny 1 wrapper: generated, do not edit */
%put NOTE: SASHINY-BEGIN run=fixture;
%let syscc = 0;
data _null_;
  call symputx('MIN_MSRP', '25000', 'G');
  call symputx('ORIGINS', '''Asia'' ''Europe'' ''USA''', 'G');
  call symputx('N_ORIGINS', '3', 'G');
run;
%put NOTE: SASHINY-BEGIN-PROGRAM;
data work.t;
  set sashelp.cars;
  where origin in (&ORIGINS) and msrp >= &MIN_MSRP;
run;
%put NOTE: SASHINY-END-PROGRAM;
%put NOTE: SASHINY-END run=fixture syscc=&syscc;
