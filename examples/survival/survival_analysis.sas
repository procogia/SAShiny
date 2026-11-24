/*----------------------------------------------------------------------------
  Program : survival_analysis.sas
  Purpose : Progression-free survival (PFS) analysis of a two-arm randomized
            clinical trial: Kaplan-Meier estimates and group comparison
            (PROC LIFETEST), Cox proportional hazards regression (PROC PHREG)
            and proportional hazards diagnostics. Requires SAS/STAT.
  Type    : Macro library. Call %survival_analysis(...) after including this
            file.
  Inputs  : ADSL   subject level (STUDYID USUBJID TRT01A AGE SEX STAGE ECOG
                   REGION ITTFL RANDDT)
            ADTTE  time to event (STUDYID USUBJID PARAMCD AVAL CNSR EVNTDESC),
                   one PFS record per subject, CNSR = 0 event, 1 censored
  Params  : STUDY       STD | NULL | NPH (study RX101-<STUDY>) | ALL (no filter)
            POPULATION  ITT (ITTFL = 'Y') | ALL
            ARMS STAGES SEXES   quoted lists, e.g. 'Control' 'RX-101'
            GROUP_BY    TRT01A | STAGE | SEX | ECOG | REGION, Kaplan-Meier groups
            CONF_LEVEL  90 | 95 | 99, for every confidence interval
            KM_TEST     logrank | wilcoxon
            SHOW_CI SHOW_CENSOR SHOW_ATRISK   yes | no, survival plot options
            MAX_FOLLOW  months; longer follow-up is censored at this time
            COX_MODEL   unadjusted (treatment only) | adjusted (treatment, age,
                        sex, stage; prespecified) | custom (treatment and
                        COVARIATES)
            COVARIATES  space-separated subset of AGE SEX STAGE ECOG REGION
            REF_TRT REF_SEX REF_STAGE   reference levels; ECOG uses 0 and
                        REGION its first level in sort order
            TIES        efron | breslow | exact
            ASSESS_PH   yes | no, supremum tests by resampling (slower)
  Outputs : WORK.RUN_STATUS, WORK.DEMOG, WORK.EVENT_SUMMARY, WORK.KM_SUMMARY,
            WORK.GROUP_TESTS, WORK.KM_RISK, WORK.KM_CURVE, WORK.KM_STEP,
            WORK.COX_ESTIMATES, WORK.COX_FIT, WORK.PH_TESTS, WORK.SURVIVAL,
            five ODS graphs in a fixed order:
              1 Kaplan-Meier curves (PROC LIFETEST)
              2 forest plot of hazard ratios
              3 log(-log(survival)) by treatment arm
              4 treatment effect over time (scaled Schoenfeld residuals)
              5 deviance residuals against the linear predictor
            Graphs 2, 4 and 5 are placeholders when the Cox model is not fitted.
  Notes   : Problems that stop the analysis (no subjects, no events) are
            ERRORs. Problems that only stop the Cox model (one treatment arm,
            a covariate with one level) are WARNINGs, and Kaplan-Meier results
            are still produced.
----------------------------------------------------------------------------*/

/* Dummy variables for a categorical covariate, against a reference level.
   Writes to the caller's macro variables _nx, _xn<i>, _xe<i>, _xl<i>, _xv<i>
   (term name, expression, label, covariate), _tst (TEST statements) and
   _notes. Uses WORK._COX0, which has C_<VAR>, the covariate as text. */
%macro _sv_cat(var, ref, lab);
  %local j n rf terms;
  %do j = 1 %to 30;
    %local _lv&j;
  %end;
  proc sql noprint;
    select distinct strip(c_&var) into :_lv1- from work._cox0
      where not missing(c_&var);
  quit;
  %let n = &sqlobs;
  %if &n < 2 %then %do;
    %put WARNING: &lab has fewer than two levels in the analysis data and is left out of the Cox model.;
    %let _notes = %superq(_notes) &lab left out (one level).;
    %return;
  %end;
  %if &n > 30 %then %do;
    %put WARNING: &lab has more than 30 levels and is left out of the Cox model.;
    %let _notes = %superq(_notes) &lab left out (over 30 levels).;
    %return;
  %end;
  %let rf = ;
  %do j = 1 %to &n;
    %if %qupcase(%superq(_lv&j)) = %qupcase(%superq(ref)) %then %let rf = &j;
  %end;
  %if %length(&rf) = 0 and %length(%superq(ref)) = 0 %then %let rf = 1;
  %else %if %length(&rf) = 0 %then %do;
    %let rf = 1;
    %put WARNING: Reference level %superq(ref) of &lab is not in the analysis data. Using %superq(_lv1) instead.;
    %let _notes = %superq(_notes) &lab reference is %superq(_lv1).;
  %end;
  %let terms = ;
  %do j = 1 %to &n;
    %if &j ne &rf %then %do;
      %let _nx = %eval(&_nx + 1);
      %let _xn&_nx = x_%lowcase(&var)_&j;
      %let _xe&_nx = (c_&var = "%superq(_lv&j)");
      %let _xl&_nx = &lab: %superq(_lv&j) vs %superq(_lv&rf);
      %let _xv&_nx = &var;
      %let terms = &terms, x_%lowcase(&var)_&j;
    %end;
  %end;
  %if %eval(&n - 1) > 1 %then
    %let _tst = %superq(_tst) &var: test %substr(%superq(terms), 3)%str(;);
%mend _sv_cat;

/* A placeholder graph, so the graph positions stay fixed */
%macro _sv_blank(ttl, msg);
  data work._blank;
    length text $200;
    x = 0; y = 0; text = "&msg";
  run;
  title "&ttl";
  proc sgplot data=work._blank noautolegend;
    text x=x y=y text=text / textattrs=(size=11pt);
    xaxis display=none;
    yaxis display=none;
  run;
  title;
%mend _sv_blank;

/* Categorical demographics rows: n (%) by arm, from WORK._DM */
%macro _sv_cnt(var, lab, ord);
  proc sql;
    create table work._dmc as
      select a.arm, &ord as ord, cats(a.&var) as level length=40,
             count(*) as n, calculated n / b.denom * 100 as pct
      from work._dm a
        join (select arm, count(*) as denom from work._dm group by arm) b
        on a.arm = b.arm
      where not missing(a.&var)
      group by a.arm, calculated level, b.denom;
  quit;
  data work._dmc;
    set work._dmc;
    length row $60 value $40;
    row = catx(', ', "&lab", level);
    value = cats(n) || ' (' || strip(put(pct, 5.1)) || '%)';
    keep arm ord row value;
  run;
  proc append base=work._dml data=work._dmc force; run;
%mend _sv_cnt;

%macro survival_analysis(adsl=work.adsl, adtte=work.adtte, study=STD,
                         population=ITT, arms='Control' 'RX-101',
                         stages='I' 'II' 'III', sexes='F' 'M', group_by=TRT01A,
                         conf_level=95, km_test=logrank, show_ci=yes,
                         show_censor=yes, show_atrisk=yes, max_follow=36,
                         cox_model=adjusted, covariates=AGE SEX STAGE,
                         ref_trt=Control, ref_sex=F, ref_stage=I, ties=efron,
                         assess_ph=no);
  %local t0 ok msg alpha _study _pop _grp _test _cox _ties _assess _cov grp_lab
         n n_adsl n_adtte n_nomatch n_bad n_events n_groups n_arms step
         cox_ok _nx _tst _notes _xlist i n_used hr_trt ph_trt km_p plot_opt
         beta_trt v;
  %do i = 1 %to 60;
    %local _xn&i _xe&i _xl&i _xv&i;
  %end;
  %let t0 = %sysfunc(datetime());
  /* Keyword values may arrive macro-quoted (SAShiny raw choices); normalise
     them into locals so the injected names are never reassigned. */
  %let _study = %upcase(%unquote(&study));
  %let _pop = %upcase(%unquote(&population));
  %let _grp = %upcase(%unquote(&group_by));
  %let _test = %lowcase(%unquote(&km_test));
  %let _cox = %lowcase(%unquote(&cox_model));
  %let _ties = %lowcase(%unquote(&ties));
  %let _assess = %lowcase(%unquote(&assess_ph));
  %let _cov = %upcase(%unquote(&covariates));
  %let ok = 1;
  %let cox_ok = 0;
  %let msg = ;
  %let _notes = ;
  %let _nx = 0;
  %let _tst = ;
  %let n = 0;
  %let n_events = 0;
  %let n_groups = 0;
  %let hr_trt = not estimated;
  %let ph_trt = not assessed;
  %let km_p = not computed;
  %let alpha = %sysevalf((100 - &conf_level) / 100);
  %if &_grp = TRT01A %then %let grp_lab = Treatment arm;
  %else %if &_grp = STAGE %then %let grp_lab = Cancer stage;
  %else %if &_grp = SEX %then %let grp_lab = Sex;
  %else %if &_grp = ECOG %then %let grp_lab = ECOG performance status;
  %else %let grp_lab = Region;

  proc datasets library=work nolist nowarn;
    delete survival demog event_summary km_summary group_tests km_risk km_curve
           km_step cox_estimates cox_fit ph_tests _dml;
  quit;

  /*------------------------------------------------------------------------
    1. Data: join ADSL and ADTTE, validate, filter
  ------------------------------------------------------------------------*/
  proc sql noprint;
    select count(*) into :n_adsl trimmed from &adsl;
    create table work._tte as
      select * from &adtte where upcase(strip(paramcd)) = 'PFS';
    select count(*) into :n_adtte trimmed from work._tte;
    select count(*) into :n_nomatch trimmed from &adsl a
      where not exists (select 1 from work._tte t where t.usubjid = a.usubjid);
    create table work._all as
      select a.studyid, a.usubjid, a.trt01a, a.age, a.sex, a.stage, a.ecog,
             a.region, a.ittfl, a.randdt, t.aval, t.cnsr, t.evntdesc
      from &adsl a join work._tte t
        on a.usubjid = t.usubjid
      where 1 = 1
        %if &_study ne ALL %then and upcase(a.studyid) = "RX101-&_study";
        %if &_pop = ITT %then and a.ittfl = 'Y';
        and a.trt01a in (&arms) and a.stage in (&stages) and a.sex in (&sexes)
      order by a.usubjid;
  quit;
  %if &n_adtte = 0 %then %do;
    %let ok = 0;
    %let msg = ADTTE has no PFS records (PARAMCD = 'PFS').;
    %put ERROR: &msg;
    %goto status;
  %end;
  %if &n_nomatch > 0 %then
    %put WARNING: &n_nomatch ADSL subject(s) have no PFS record and are left out.;

  /* Invalid records are reported and dropped; longer follow-up is censored */
  data work.survival work._bad;
    set work._all;
    length group $40 status $12;
    if missing(aval) or aval < 0 or cnsr not in (0, 1) then do;
      output work._bad;
      return;
    end;
    if aval > &max_follow then do;
      aval = &max_follow;
      cnsr = 1;
      evntdesc = 'Censored at maximum follow-up';
    end;
    %if &_grp = TRT01A %then %do; group = trt01a; %end;
    %else %if &_grp = STAGE %then %do; group = catx(' ', 'Stage', stage); %end;
    %else %if &_grp = SEX %then %do; group = ifc(sex = 'F', 'Female', ifc(sex = 'M', 'Male', sex)); %end;
    %else %if &_grp = ECOG %then %do; group = catx(' ', 'ECOG', ecog); %end;
    %else %do; group = region; %end;
    if missing(group) then group = 'Missing';
    status = ifc(cnsr = 0, 'Event', 'Censored');
    label aval = 'PFS (months)' cnsr = 'Censored (1 = yes)' group = "&grp_lab"
          status = 'Status' evntdesc = 'Event or censoring reason';
    output work.survival;
  run;

  proc sql noprint;
    select count(*) into :n_bad trimmed from work._bad;
    select count(*), sum(cnsr = 0), count(distinct group), count(distinct trt01a)
      into :n trimmed, :n_events trimmed, :n_groups trimmed, :n_arms trimmed
      from work.survival;
  quit;
  %if &n_bad > 0 %then
    %put WARNING: &n_bad record(s) with a missing or negative AVAL, or CNSR not 0 or 1, are left out.;
  %if &n = 0 %then %do;
    %let ok = 0;
    %let msg = No subjects match the selected study, population and filters.;
    %put ERROR: &msg;
    %goto status;
  %end;
  %if &n_events = 0 %then %do;
    %let ok = 0;
    %let msg = The &n selected subjects have no events, so survival cannot be estimated.;
    %put ERROR: &msg;
    %goto status;
  %end;
  %if &n_events < 10 %then
    %put WARNING: Only &n_events events. Estimates will be very imprecise.;

  /*------------------------------------------------------------------------
    2. Descriptive statistics by treatment arm
  ------------------------------------------------------------------------*/
  data work._dm;
    set work.survival(in=a) work.survival(in=b);
    length arm $40;
    arm = ifc(b, 'Total', trt01a);
  run;
  proc sql;
    create table work._dml as
      select arm, 1 as ord, 'Subjects, n' as row length=60,
             cats(count(*)) as value length=40
        from work._dm group by arm
      union all
      select arm, 2, 'Age (years), mean (SD)',
             strip(put(mean(age), 5.1)) || ' (' || strip(put(std(age), 5.1)) || ')'
        from work._dm group by arm
      union all
      select arm, 3, 'Age (years), median (min, max)',
             strip(put(median(age), 5.1)) || ' (' || cats(min(age)) || ', ' || cats(max(age)) || ')'
        from work._dm group by arm;
  quit;
  %_sv_cnt(sex, Sex, 4)
  %_sv_cnt(stage, Stage, 5)
  %_sv_cnt(ecog, ECOG, 6)
  %_sv_cnt(region, Region, 7)

  /* One column per arm, then Total; labels carry the arm size */
  proc sql;
    create table work._arms as
      select arm, count(*) as n_arm,
             case when arm = 'Total' then 2 else 1 end as last
      from work._dm group by arm order by last, arm;
  quit;
  data work._arms;
    set work._arms;
    col = _n_;
    length collab $60;
    collab = catx(' ', arm, cats('(N=', n_arm, ')'));
  run;
  proc sql;
    create table work._dml2 as
      select d.ord, d.row, d.value, a.col, a.collab
      from work._dml d join work._arms a on d.arm = a.arm
      order by d.ord, d.row, a.col;
  quit;
  proc transpose data=work._dml2 out=work.demog(drop=_name_) prefix=arm_;
    by ord row;
    id col;
    idlabel collab;
    var value;
  run;
  data work.demog;
    set work.demog;
    label row = 'Characteristic';
    drop ord;
  run;

  /* Events, censoring and median follow-up (reverse Kaplan-Meier) */
  ods graphics off;
  ods output Quartiles=work._fu;
  proc lifetest data=work._dm;
    time aval * cnsr(0);
    strata arm / notest;
  run;
  proc sql;
    create table work.event_summary as
      select a.col, d.arm label='Treatment arm',
             count(*) as n label='Subjects',
             sum(d.cnsr = 0) as events label='Events',
             sum(d.evntdesc = 'Disease progression') as progression label='Progression',
             sum(d.evntdesc = 'Death') as death label='Death',
             sum(d.cnsr = 1) as censored label='Censored',
             sum(d.evntdesc = 'Lost to follow-up') as ltfu label='Lost to follow-up',
             calculated censored / calculated n * 100 as pct_cens
               label='Censored (%)' format=5.1,
             (select f.estimate from work._fu f where f.arm = d.arm and f.percent = 50)
               as median_fu label='Median follow-up (months)' format=6.1
      from work._dm d join work._arms a on d.arm = a.arm
      group by a.col, d.arm
      order by a.col;
  quit;
  data work.event_summary;
    set work.event_summary;
    drop col;
  run;

  /*------------------------------------------------------------------------
    3. Kaplan-Meier estimates and group comparison (PROC LIFETEST)
  ------------------------------------------------------------------------*/
  %if &max_follow <= 12 %then %let step = 3;
  %else %if &max_follow <= 36 %then %let step = 6;
  %else %let step = 12;
  %let plot_opt = ;
  %if %lowcase(&show_ci) = yes %then %let plot_opt = &plot_opt cl;
  %if %lowcase(&show_censor) = no %then %let plot_opt = &plot_opt nocensor;
  %if %lowcase(&show_atrisk) = yes %then
    %let plot_opt = &plot_opt atrisk(outside)=0 to &max_follow by &step;
  %if &n_groups > 1 %then %let plot_opt = &plot_opt test;

  ods graphics on / width=8in height=5.5in;
  ods output Quartiles=work._quart CensoredSummary=work._cs
    %if &n_groups > 1 %then HomTests=work._hom;
    ;
  title "1. Kaplan-Meier estimate of progression-free survival by %lowcase(&grp_lab)";
  proc lifetest data=work.survival alpha=&alpha outsurv=work._km
                plots=survival%if %length(&plot_opt) %then (&plot_opt);;
    time aval * cnsr(1);
    %if &n_groups > 1 %then %do;
      strata group / test=&_test;
    %end;
  run;
  title;
  %if &n_groups = 1 %then %do;
    %put WARNING: All selected subjects are in one group (%lowcase(&grp_lab)), so groups are not compared.;
    data work._km; set work._km; length group $40; group = 'All subjects'; run;
    data work._quart; set work._quart; length group $40; group = 'All subjects'; run;
    data work._cs; set work._cs; length group $40; group = 'All subjects'; run;
  %end;

  /* Survival estimates. OUTSURV leaves the confidence limits (and sometimes
     the estimate) missing on censored rows: carry each one forward */
  data work.km_curve;
    set work._km;
    by group notsorted;
    retain _s _l _u;
    if first.group then call missing(_s, _l, _u);
    if missing(survival) then survival = _s; else _s = survival;
    if missing(sdf_lcl) then sdf_lcl = _l; else _l = sdf_lcl;
    if missing(sdf_ucl) then sdf_ucl = _u; else _u = sdf_ucl;
    if survival = 0 then call missing(sdf_lcl, sdf_ucl);
    censored = (_censor_ = 1);
    label group = "&grp_lab" aval = 'Month' survival = 'Survival probability'
          sdf_lcl = "Lower &conf_level% limit" sdf_ucl = "Upper &conf_level% limit"
          censored = 'Censored';
    format survival sdf_lcl sdf_ucl 6.4 aval 6.2;
    keep group aval survival sdf_lcl sdf_ucl censored;
  run;

  /* Step-function points for the SAShiny chart: (t, S before) and (t, S after) */
  data work.km_step;
    set work.km_curve(where=(not censored));
    by group notsorted;
    retain prev;
    time = aval;
    if first.group then prev = 1;
    else do; survival_ = survival; survival = prev; output; survival = survival_; end;
    output;
    prev = survival;
    label time = 'Month' survival = 'Survival probability' group = "&grp_lab";
    keep group time survival;
  run;
  /* Extend each curve to its last follow-up time */
  data work._ends;
    set work.km_curve;
    by group notsorted;
    if last.group;
    time = aval;
    keep group time survival;
  run;
  data work.km_step;
    set work.km_step work._ends;
  run;
  proc sort data=work.km_step; by group time descending survival; run;

  /* Median survival and 12- and 24-month survival rates */
  data work._lm;
    set work.km_curve;
    by group notsorted;
    retain s12 l12 u12 s24 l24 u24;
    if first.group then call missing(s12, l12, u12, s24, l24, u24);
    if aval <= 12 then do; s12 = survival; l12 = sdf_lcl; u12 = sdf_ucl; end;
    if aval <= 24 then do; s24 = survival; l24 = sdf_lcl; u24 = sdf_ucl; end;
    /* A landmark beyond the last follow-up time is not estimable */
    if last.group then do;
      if aval < 12 then call missing(s12, l12, u12);
      if aval < 24 then call missing(s24, l24, u24);
      output;
    end;
    keep group s12 l12 u12 s24 l24 u24;
  run;
  proc sql;
    create table work.km_summary as
      select q.group label="&grp_lab",
             c.total as n label='Subjects', c.failed as events label='Events',
             c.censored label='Censored',
             case when missing(q.estimate) then 'Not reached'
                  else catx(' ', put(q.estimate, 5.1),
                            cats('(', ifc(missing(q.lowerlimit), 'NR', put(q.lowerlimit, 5.1)), ',') || ' ' || cats(
                                 ifc(missing(q.upperlimit), 'NR', put(q.upperlimit, 5.1)), ')'))
             end as median length=40 label="Median PFS, months (&conf_level% CI)",
             case when missing(l.s12) then 'Not estimable'
                  else catx(' ', put(l.s12 * 100, 5.1),
                            cats('(', put(l.l12 * 100, 5.1), ',') || ' ' || cats(put(l.u12 * 100, 5.1), ')'))
             end as pfs12 length=40 label="12-month PFS, % (&conf_level% CI)",
             case when missing(l.s24) then 'Not estimable'
                  else catx(' ', put(l.s24 * 100, 5.1),
                            cats('(', put(l.l24 * 100, 5.1), ',') || ' ' || cats(put(l.u24 * 100, 5.1), ')'))
             end as pfs24 length=40 label="24-month PFS, % (&conf_level% CI)"
      from work._quart(where=(percent = 50)) q
        left join work._lm l on q.group = l.group
        left join work._cs
          %if &n_groups > 1 %then (where=(not missing(stratum)));
          c on q.group = c.group
      order by q.group;
  quit;

  /* Number at risk */
  proc sql;
    create table work.km_risk as
      select group label="&grp_lab"
        %do i = 0 %to &max_follow %by &step;
          , sum(aval >= &i) as m_&i label="Month &i"
        %end;
      from work.survival group by group order by group;
  quit;

  %if &n_groups > 1 %then %do;
    data work.group_tests;
      retain comparison test chisq df probchisq verdict;
      set work._hom;
      length comparison $40 verdict $60;
      comparison = "&grp_lab";
      if probchisq < 0.05 then verdict = 'Survival differs between groups (p < 0.05)';
      else verdict = 'No significant difference (p >= 0.05)';
      label test = 'Test' comparison = 'Groups compared' chisq = 'Chi-square' df = 'DF'
            probchisq = 'p value' verdict = 'Verdict';
      format chisq 8.3 probchisq pvalue6.4;
      keep comparison test chisq df probchisq verdict;
    run;
    proc sql noprint;
      select catx(' ', test, 'p =', put(probchisq, pvalue6.4)) into :km_p trimmed
        from work.group_tests;
    quit;
  %end;
  %else %do;
    data work.group_tests;
      length comparison $40 test $20 verdict $60;
      comparison = "&grp_lab"; test = "%sysfunc(propcase(&_test))"; chisq = .; df = .; probchisq = .;
      verdict = 'Not computed: fewer than two groups';
      label test = 'Test' comparison = 'Groups compared' chisq = 'Chi-square' df = 'DF'
            probchisq = 'p value' verdict = 'Verdict';
    run;
  %end;

  /*------------------------------------------------------------------------
    4. Cox proportional hazards regression (PROC PHREG)
  ------------------------------------------------------------------------*/
  data work._cox0;
    set work.survival;
    length c_trt01a c_sex c_stage c_ecog c_region $40;
    c_trt01a = trt01a; c_sex = sex; c_stage = stage; c_region = region;
    if not missing(ecog) then c_ecog = cats(ecog);
  run;

  %let _notes = ;
  %_sv_cat(TRT01A, %unquote(&ref_trt), Treatment)
  %if &_nx = 0 %then %do;
    %let msg = The Cox model needs both treatment arms in the analysis data.;
    %put WARNING: &msg The Cox model and its diagnostics are skipped.;
    %goto km_lml;
  %end;
  %let cox_ok = 1;
  %if &_cox = adjusted %then %let _cov = AGE SEX STAGE;
  %else %if &_cox = unadjusted %then %let _cov = ;
  %do i = 1 %to %sysfunc(countw(&_cov, %str( )));
    %let v = %scan(&_cov, &i, %str( ));
    %if &v = AGE %then %do;
      %let _nx = %eval(&_nx + 1);
      %let _xn&_nx = x_age10;
      %let _xe&_nx = age / 10;
      %let _xl&_nx = Age (per 10 years);
      %let _xv&_nx = AGE;
    %end;
    %else %if &v = SEX %then %_sv_cat(SEX, %unquote(&ref_sex), Sex);
    %else %if &v = STAGE %then %_sv_cat(STAGE, %unquote(&ref_stage), Stage);
    %else %if &v = ECOG %then %_sv_cat(ECOG, 0, ECOG);
    %else %if &v = REGION %then %_sv_cat(REGION, , Region);
  %end;

  %let _xlist = ;
  %do i = 1 %to &_nx;
    %let _xlist = &_xlist &&_xn&i;
  %end;
  data work._cox;
    set work._cox0;
    %do i = 1 %to &_nx;
      %if &&_xv&i = AGE %then %do;
        &&_xn&i = &&_xe&i;
      %end;
      %else %do;
        if missing(c_&&_xv&i) then &&_xn&i = .;
        else &&_xn&i = &&_xe&i;
      %end;
    %end;
    _used = (nmiss(of &_xlist) = 0);
  run;
  data work._terms;
    length term $32 label $80 variable $16;
    %do i = 1 %to &_nx;
      term = "&&_xn&i"; label = "&&_xl&i"; variable = "&&_xv&i"; order = &i; output;
    %end;
  run;
  proc sql noprint;
    select sum(_used) into :n_used trimmed from work._cox;
  quit;
  %if &n_used < &n %then
    %put WARNING: %eval(&n - &n_used) subject(s) with a missing covariate are left out of the Cox model.;

  ods graphics off;
  ods output ParameterEstimates=work._pe FitStatistics=work._fit GlobalTests=work._glob
    %if %length(%superq(_tst)) %then TestStmts=work._tsts;
    ;
  proc phreg data=work._cox;
    model aval * cnsr(1) = &_xlist / ties=&_ties rl alpha=&alpha;
    %unquote(%superq(_tst))
    output out=work._res xbeta=xbeta resdev=resdev
           wtressch=%do i = 1 %to &_nx; ws_&i %end;;
  run;
  %if not %sysfunc(exist(work._pe)) %then %do;
    %let cox_ok = 0;
    %let msg = PROC PHREG did not fit the Cox model. See the SAS log.;
    %put WARNING: &msg;
    %goto km_lml;
  %end;

  proc sql;
    create table work.cox_estimates as
      select t.label as term label='Term', t.variable label='Covariate',
             p.estimate label='Log hazard ratio' format=8.4,
             p.stderr as std_error label='Std error' format=8.4,
             p.hazardratio as hazard_ratio label='Hazard ratio' format=6.3,
             p.hrlowercl as hr_lower label="Lower &conf_level% limit" format=6.3,
             p.hruppercl as hr_upper label="Upper &conf_level% limit" format=6.3,
             catx(' ', put(p.hazardratio, 5.2),
                  cats('(', put(p.hrlowercl, 5.2), ',') || ' ' || cats(put(p.hruppercl, 5.2), ')'))
               as hr_ci length=30 label="HR (&conf_level% CI)",
             p.probchisq as p_value label='p value' format=pvalue6.4
      from work._pe p join work._terms t on upcase(p.parameter) = upcase(t.term)
      order by t.order;
    select hr_ci, estimate into :hr_trt trimmed, :beta_trt trimmed
      from work.cox_estimates where variable = 'TRT01A';
  quit;

  data work.cox_fit;
    length section $24 item $40 value $80;
    set work._fit(in=f) work._glob(in=g)
      %if %length(%superq(_tst)) %then work._tsts(in=t);
      ;
    if f then do;
      section = 'Model fit';
      item = criterion;
      value = catx(' ', 'without covariates', put(withoutcovariates, 10.2),
                   '| with covariates', put(withcovariates, 10.2));
    end;
    else if g then do;
      section = 'Global null hypothesis';
      item = test;
      value = catx(' ', 'Chi-square', put(chisq, 8.2), '| DF', df, '| p',
                   put(probchisq, pvalue6.4));
    end;
    %if %length(%superq(_tst)) %then %do;
    else if t then do;
      section = 'Joint test of levels';
      item = label;
      value = catx(' ', 'Wald chi-square', put(waldchisq, 8.2), '| DF', df, '| p',
                   put(probchisq, pvalue6.4));
    end;
    %end;
    label section = 'Section' item = 'Statistic' value = 'Value';
    keep section item value;
  run;

  /* Forest plot */
  ods graphics on / width=8in height=%sysfunc(max(3, %sysevalf(1.5 + 0.45 * &_nx)))in;
  title "2. Hazard ratios with &conf_level% confidence intervals (&_cox Cox model)";
  footnote j=l h=8pt 'Hazard ratio < 1: lower hazard of progression or death than the reference.';
  proc sgplot data=work.cox_estimates noautolegend;
    scatter y=term x=hazard_ratio / xerrorlower=hr_lower xerrorupper=hr_upper
            markerattrs=(symbol=squarefilled size=9);
    refline 1 / axis=x lineattrs=(pattern=dash);
    yaxistable hr_ci p_value / location=inside position=right;
    xaxis type=log label='Hazard ratio (log scale)' grid;
    yaxis discreteorder=data reverse display=(nolabel);
  run;
  title;
  footnote;

  /*------------------------------------------------------------------------
    5. Diagnostics: proportional hazards
  ------------------------------------------------------------------------*/
  /* Scaled Schoenfeld residuals against the rank of event time:
     a correlation away from zero means the effect changes over time */
  data work._sch;
    set work._res(where=(cnsr = 0));
  run;
  proc rank data=work._sch out=work._sch ties=mean;
    var aval;
    ranks rank_time;
  run;
  proc corr data=work._sch nosimple outp=work._cp noprint;
    var rank_time;
    with %do i = 1 %to &_nx; ws_&i %end;;
  run;
  data work.ph_tests;
    length method $60 term $80 verdict $60;
    set work._cp(where=(_type_ = 'CORR'));
    i = input(scan(_name_, 2, '_'), 8.);
    set work._terms point=i;
    method = 'Schoenfeld residuals vs rank of time';
    statistic = rank_time;
    /* Fisher z test of a zero correlation, on the number of events */
    n_ev = &n_events;
    z = 0.5 * log((1 + statistic) / (1 - statistic)) * sqrt(n_ev - 3);
    p_value = 2 * (1 - probnorm(abs(z)));
    term = label;
    verdict = ifc(p_value < 0.05, 'Evidence of non-proportional hazards',
                  'No evidence against proportional hazards');
    keep method term statistic p_value verdict;
  run;

  %if &_assess = yes %then %do;
    ods graphics off;
    ods select ProportionalHazardsSupTest;
    ods output ProportionalHazardsSupTest=work._sup;
    proc phreg data=work._cox;
      model aval * cnsr(1) = &_xlist / ties=&_ties;
      assess ph / resample=1000 seed=20231;
    run;
    ods select all;
    proc sql;
      create table work._sup2 as
        select 'Supremum test (ASSESS PH, 1,000 resamples)' as method length=60,
               t.label as term length=80, s.maxabsvalue as statistic,
               s.pvalue as p_value,
               case when s.pvalue < 0.05 then 'Evidence of non-proportional hazards'
                    else 'No evidence against proportional hazards' end as verdict length=60
        from work._sup s join work._terms t on upcase(s.variable) = upcase(t.term)
        order by t.order;
    quit;
    proc append base=work.ph_tests data=work._sup2; run;
  %end;
  %else %do;
    data work._sup2;
      length method $60 term $80 verdict $60;
      method = 'Supremum test (ASSESS PH)'; term = 'Not requested';
      statistic = .; p_value = .;
      verdict = 'Turn on the resampling test to run it';
    run;
    proc append base=work.ph_tests data=work._sup2; run;
  %end;
  data work.ph_tests;
    retain method term statistic p_value verdict;
    set work.ph_tests;
    label method = 'Method' term = 'Term' statistic = 'Statistic (correlation or sup |W|)'
          p_value = 'p value' verdict = 'Verdict';
    format statistic 8.4 p_value pvalue6.4;
  run;
  proc sql noprint;
    select catx(' ', verdict, '(p = ' || strip(put(p_value, pvalue6.4)) || ')') into :ph_trt trimmed
      from work.ph_tests
      where method = 'Schoenfeld residuals vs rank of time' and term = "&_xl1";
  quit;

%km_lml:
  /* Graphs are collected by position (select: in the contract), so when the Cox model
     was skipped (one arm, or PROC PHREG failed) its forest plot is still graph 2. */
  %if not &cox_ok %then %do;
    ods graphics on / width=8in height=3in;
    %_sv_blank(%str(2. Hazard ratios), %str(Cox model not fitted: &msg))
  %end;

  /* Log(-log(survival)) by treatment arm: parallel curves support PH */
  ods graphics off;
  proc lifetest data=work.survival outsurv=work._kmt noprint;
    time aval * cnsr(1);
    strata trt01a / notest;
  run;
  data work._lml;
    set work._kmt(where=(_censor_ = 0 and 0 < survival < 1 and aval > 0));
    lml = log(-log(survival));
    log_t = log(aval);
  run;
  ods graphics on / width=8in height=4.5in;
  title '3. Log(-log(survival)) against log(month) by treatment arm';
  footnote j=l h=8pt 'Roughly parallel curves support the proportional hazards assumption for treatment.';
  proc sgplot data=work._lml;
    step x=log_t y=lml / group=trt01a lineattrs=(thickness=2);
    xaxis label='Log(month)' grid;
    yaxis label='Log(-log(survival))' grid;
    keylegend / title='Treatment arm';
  run;
  title;
  footnote;

  %if &cox_ok %then %do;
    data work._bt;
      set work._sch;
      beta_t = ws_1 + &beta_trt;
    run;
    title "4. Treatment effect over time: &_xl1";
    footnote j=l h=8pt 'Scaled Schoenfeld residuals plus the estimate. A flat smooth means a constant hazard ratio.';
    proc sgplot data=work._bt;
      scatter x=aval y=beta_t / markerattrs=(size=5) transparency=0.5 legendlabel='Event';
      loess x=aval y=beta_t / nomarkers smooth=0.5 lineattrs=(thickness=2) legendlabel='Loess smooth';
      refline &beta_trt / axis=y label='Cox estimate' lineattrs=(pattern=dash);
      refline 0 / axis=y label='No effect' lineattrs=(pattern=dot);
      xaxis label='Month' grid;
      yaxis label='Log hazard ratio at time t' grid;
    run;
    title '5. Deviance residuals against the linear predictor';
    footnote j=l h=8pt 'Points far outside +/-2 are subjects the model fits poorly.';
    proc sgplot data=work._res;
      scatter x=xbeta y=resdev / group=status markerattrs=(size=5) transparency=0.4;
      loess x=xbeta y=resdev / nomarkers lineattrs=(thickness=2) legendlabel='Loess smooth';
      refline -2 0 2 / axis=y lineattrs=(pattern=dash);
      xaxis label='Linear predictor (X*beta)' grid;
      yaxis label='Deviance residual' grid;
    run;
    title;
    footnote;
  %end;
  %else %do;
    ods graphics on / width=8in height=3in;
    %_sv_blank(%str(4. Treatment effect over time), %str(Cox model not fitted: &msg))
    %_sv_blank(%str(5. Deviance residuals), %str(Cox model not fitted: &msg))
    /* Same columns as the fitted table, so the forest plot's chart columns resolve. */
    data work.cox_estimates;
      length term $80 hr_ci $120;
      term = 'Cox model not fitted'; hr_ci = "&msg";
      hazard_ratio = .; hr_lower = .; hr_upper = .; p_value = .;
      label term = 'Term' hazard_ratio = 'Hazard ratio' hr_lower = "Lower &conf_level% limit"
            hr_upper = "Upper &conf_level% limit" hr_ci = 'Note' p_value = 'p value';
    run;
    data work.cox_fit;
      length section $24 item $40 value $80;
      section = 'Cox model'; item = 'Not fitted'; value = "&msg";
      label section = 'Section' item = 'Statistic' value = 'Value';
    run;
    data work.ph_tests;
      length method $60 term $80 verdict $60;
      method = 'Not assessed'; term = 'Cox model not fitted'; statistic = .; p_value = .;
      verdict = "&msg";
      label method = 'Method' term = 'Term' statistic = 'Statistic' p_value = 'p value'
            verdict = 'Verdict';
    run;
  %end;
  ods graphics / reset;

  /*------------------------------------------------------------------------
    6. Run status
  ------------------------------------------------------------------------*/
%status:
  %if not &ok %then %do;
    /* Empty result tables, so the outputs still collect */
    %local ds;
    %do i = 1 %to 10;
      %let ds = %scan(demog event_summary km_summary group_tests km_risk km_curve km_step cox_estimates cox_fit ph_tests, &i);
      %if not %sysfunc(exist(work.&ds)) %then %do;
        data work.&ds;
          length note $120;
          note = "Not computed: &msg";
          label note = 'Note';
        run;
      %end;
    %end;
    %if not %sysfunc(exist(work.survival)) %then %do;
      data work.survival; length note $120; note = "&msg"; run;
    %end;
  %end;
  data work.run_status;
    length item $40 value $200;
    label item = 'Item' value = 'Value';
    item = 'Status'; value = ifc(&ok, ifc(&cox_ok, 'Completed', 'Completed without the Cox model'), 'Failed'); output;
    %if %length(&msg) %then %do;
      item = 'Message'; value = "&msg"; output;
    %end;
    item = 'Study'; value = ifc("&_study" = 'ALL', 'All studies in the file', "RX101-&_study"); output;
    item = 'Population'; value = ifc("&_pop" = 'ITT', 'Intent-to-treat (ITTFL = Y)', 'All subjects'); output;
    %if &ok %then %do;
      item = 'Subjects analysed'; value = catx(' ', &n, 'subjects,', &n_events, 'events'); output;
      item = 'Maximum follow-up'; value = "&max_follow months"; output;
      item = 'Kaplan-Meier groups'; value = catx(' ', "&grp_lab:", &n_groups, 'groups'); output;
      item = 'Group comparison'; value = "&km_p"; output;
      item = 'Cox model'; value = catx(' ', "&_cox,", "&_nx", 'term(s), ties =', "&_ties"); output;
      item = 'Treatment hazard ratio'; value = "&hr_trt"; output;
      item = 'Proportional hazards (treatment)'; value = "&ph_trt"; output;
      %if %length(%superq(_notes)) %then %do;
        item = 'Model notes'; value = "%superq(_notes)"; output;
      %end;
    %end;
  run;
  /* Timing goes to the log, so the same inputs always give identical tables */
  %put NOTE: survival_analysis finished in %sysfunc(putn(%sysevalf(%sysfunc(datetime()) - &t0), 8.1)) seconds.;

  proc datasets library=work nolist nowarn;
    delete _tte _all _bad _dm _dml _dmc _dml2 _arms _fu _quart _cs _hom _km _ends
           _lm _cox0 _cox _terms _pe _fit _glob _tsts _res _sch _cp _sup _sup2
           _kmt _lml _bt _blank;
  quit;
%mend survival_analysis;
