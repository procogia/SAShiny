/* SAShiny 1 wrapper: generated, do not edit */
%put NOTE: SASHINY-BEGIN run=fixture;
%let syscc = 0;
data _null_;
  call symputx('NOTE', 'It''s 100% & done', 'G');
run;
%let NOTE = %superq(NOTE);
%put NOTE: SASHINY-BEGIN-PROGRAM;
data work.t;
  set sashelp.cars;
run;
%put NOTE: SASHINY-END-PROGRAM;
%put NOTE: SASHINY-END run=fixture syscc=&syscc;
