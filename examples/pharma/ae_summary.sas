/*----------------------------------------------------------------------------
  Program : ae_summary.sas
  Purpose : Treatment-emergent adverse event (TEAE) incidence by system organ
            class and preferred term, plus a demographics summary.
  Type    : Macro library. Call %ae_summary(...) after including this file.
  Inputs  : WORK.ADSL  (USUBJID, TRT01A, SAFFL, AGE, SEX)
            WORK.ADAE  (USUBJID, AEBODSYS, AEDECOD, ASTDT, TRTEMFL)
  Params  : ARMS      quoted list of actual treatments, e.g. 'Placebo'
            SAFFL     safety population flag value, e.g. 'Y'
            START_DT  first AE start date, SAS date literal, e.g. '01JAN2025'd
            END_DT    last AE start date, SAS date literal
            MIN_PCT   minimum incidence (%) in any arm for a term to be shown
  Outputs : WORK.BIGN, WORK.DEMOG, WORK.AE_SOC_PT, one ODS graph, two reports
----------------------------------------------------------------------------*/

%macro ae_summary(arms=, saffl='Y', start_dt=, end_dt=, min_pct=0);

  /* Analysis population */
  data work._adsl;
    set work.adsl;
    where saffl = &saffl and trt01a in (&arms);
  run;

  proc sql noprint;
    /* Denominators per arm */
    create table work.bign as
      select trt01a, count(distinct usubjid) as bign label='Subjects (N)'
      from work._adsl
      group by trt01a;

    /* Demographics */
    create table work.demog as
      select trt01a label='Actual treatment',
             count(distinct usubjid) as n label='N',
             mean(age) as mean_age label='Mean age' format=5.1,
             std(age) as sd_age label='SD age' format=5.1,
             min(age) as min_age label='Min age',
             max(age) as max_age label='Max age',
             sum(sex = 'F') / count(*) * 100 as pct_female label='Female (%)' format=5.1
      from work._adsl
      group by trt01a;

    /* TEAEs in the analysis window */
    create table work._teae as
      select distinct s.usubjid, s.trt01a, e.aebodsys, e.aedecod
      from work._adsl as s
           inner join work.adae as e
             on s.usubjid = e.usubjid
      where e.trtemfl = 'Y' and e.astdt between &start_dt and &end_dt;

    /* Incidence per arm */
    create table work._incidence as
      select t.trt01a, t.aebodsys, t.aedecod,
             count(distinct t.usubjid) as n_subj label='n',
             calculated n_subj / b.bign * 100 as pct label='%' format=5.1
      from work._teae as t
           inner join work.bign as b
             on t.trt01a = b.trt01a
      group by t.trt01a, t.aebodsys, t.aedecod, b.bign;

    /* Keep terms reaching MIN_PCT in at least one arm */
    create table work.ae_soc_pt as
      select i.*
      from work._incidence as i
      where i.aedecod in (select aedecod from work._incidence group by aedecod having max(pct) >= &min_pct)
      order by i.aebodsys, i.aedecod, i.trt01a;
  quit;

  ods graphics / width=8in height=6in;

  title 'Treatment-emergent adverse events by preferred term';
  title2 "Terms with incidence of at least &min_pct percent in any arm";
  proc sgplot data=work.ae_soc_pt;
    hbar aedecod / response=pct group=trt01a groupdisplay=cluster;
    xaxis label='Subjects with event (%)' grid;
    yaxis display=(nolabel);
  run;

  title 'Demographics: safety population';
  title2;
  proc print data=work.demog noobs label;
  run;

  title 'TEAE incidence by system organ class and preferred term';
  proc report data=work.ae_soc_pt nowd split='~';
    column aebodsys aedecod trt01a,(n_subj pct);
    define aebodsys / group 'System organ class' flow width=30;
    define aedecod  / group 'Preferred term' flow width=30;
    define trt01a   / across 'Actual treatment';
    define n_subj   / analysis sum 'n' format=4.;
    define pct      / analysis sum '%' format=5.1;
  run;
  title;

  proc datasets library=work nolist nowarn;
    delete _adsl _teae _incidence;
  quit;

%mend ae_summary;
