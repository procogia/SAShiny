/* SAShiny 1 wrapper: generated, do not edit */
%put NOTE: SASHINY-BEGIN run=fixture;
%let syscc = 0;
%put NOTE: SASHINY-BEGIN-PROGRAM;
%macro empty();
  %put NOTE: empty;
%mend empty;
%empty();
%put NOTE: SASHINY-END-PROGRAM;
%put NOTE: SASHINY-END run=fixture syscc=&syscc;
