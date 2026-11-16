/* SAShiny 1 wrapper: generated, do not edit */
%put NOTE: SASHINY-BEGIN run=fixture;
%let syscc = 0;
data _null_;
  call symputx('WHO', '''O''''Brien & Co, (50%''', 'G');
  call symputx('NOTE', 'R&D x); %put 100%', 'G');
  call symputx('TAG', '"say ""hi"", 5%"', 'G');
run;
%let NOTE = %superq(NOTE);
%put NOTE: SASHINY-BEGIN-PROGRAM;
%macro special(who=, note=, tag=);
  %put NOTE: &who &note &tag;
%mend special;
%special(WHO='O''Brien & Co, (50%', NOTE=R%nrstr(&)D x%nrstr(%))%nrstr(;) %nrstr(%%)put 100%nrstr(%%), TAG="say ""hi"", 5%nrstr(%%)");
%put NOTE: SASHINY-END-PROGRAM;
%put NOTE: SASHINY-END run=fixture syscc=&syscc;
