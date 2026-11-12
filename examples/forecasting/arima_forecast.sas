/*----------------------------------------------------------------------------
  Program : arima_forecast.sas
  Purpose : Monthly prescription demand forecasting with ARIMA / seasonal
            ARIMA (PROC ARIMA, SAS/ETS). Fits a curated set of candidate
            models on a training window, scores them on a holdout window,
            refits the chosen model on all months and forecasts ahead.
  Type    : Macro library. Call %arima_forecast(...) after including this file.
  Inputs  : RX_DATA      monthly data (MONTH, PRODUCT, REGION, PRESCRIPTIONS,
                         optional SHOCK_FLAG)
  Params  : PRODUCT      product, quoted, e.g. 'Drug A'
            REGION       region, quoted, e.g. 'West'
            START_DT     first month used, SAS date literal
            END_DT       last month used, SAS date literal
            TRANSFORM    none | log
            MA_WINDOW    moving-average window (months) for the history chart
            HOLDOUT      months held out to score the candidates
            METRIC       rmse | mae | wape, ranks the candidates
            FINAL_MODEL  best (lowest holdout METRIC) | custom | m1-m8
            AR_P DIFF_D MA_Q          custom non-seasonal orders p, d, q
            SAR_P SDIFF_D SMA_Q       custom seasonal orders P, D, Q (period 12)
            HORIZON      months to forecast
            CONF_LEVEL   prediction interval level (%)
  Outputs : WORK.RUN_STATUS, WORK.SERIES, WORK.MODEL_COMPARISON,
            WORK.ESTIMATES, WORK.WHITE_NOISE, WORK.DIAGNOSTICS, WORK.FORECAST,
            nine ODS graphs in a fixed order:
              1 history and moving average   2 seasonal profile
              3 ACF / PACF                   4 candidate holdout scores
              5 holdout forecasts vs actual  6 residuals over time
              7 residual ACF                 8 residual histogram
              9 history and forecast
  Notes   : Requires SAS/ETS (PROC ARIMA, PROC EXPAND). Candidates that do not
            converge are excluded from automatic selection; PROC ARIMA's
            messages about them stay in the log.
----------------------------------------------------------------------------*/

/* Model orders -> PROC ARIMA syntax in &_dif &_ar &_ma &_int, and a name in &_name */
%macro _fc_spec(p, d, q, sp, sd, sq);
  %local lags i;
  %global _dif _ar _ma _int _name;
  %let _dif = ;
  %if &d = 1 and &sd = 1 %then %let _dif = (1,12);
  %else %if &d = 1 %then %let _dif = (1);
  %else %if &sd = 1 %then %let _dif = (12);

  %let lags = ;
  %do i = 1 %to &p;
    %if &i = 1 %then %let lags = 1;
    %else %let lags = &lags,&i;
  %end;
  %if &p > 0 and &sp = 1 %then %let _ar = p=(&lags)(12);
  %else %if &p > 0 %then %let _ar = p=(&lags);
  %else %if &sp = 1 %then %let _ar = p=(12);
  %else %let _ar = ;

  %let lags = ;
  %do i = 1 %to &q;
    %if &i = 1 %then %let lags = 1;
    %else %let lags = &lags,&i;
  %end;
  %if &q > 0 and &sq = 1 %then %let _ma = q=(&lags)(12);
  %else %if &q > 0 %then %let _ma = q=(&lags);
  %else %if &sq = 1 %then %let _ma = q=(12);
  %else %let _ma = ;

  /* Differenced models have no intercept; undifferenced ones keep the mean */
  %if %eval(&d + &sd) > 0 %then %let _int = noint;
  %else %let _int = ;

  %if %eval(&sp + &sd + &sq) > 0 %then %let _name = SARIMA(&p,&d,&q)(&sp,&sd,&sq)[12];
  %else %let _name = ARIMA(&p,&d,&q);
%mend _fc_spec;

/* Back-transform a model-scale forecast to prescriptions */
%macro _fc_back(f, std, l, u);
  %if &_log %then %do;
    &f = exp(&f + 0.5 * &std**2);
    &l = exp(&l);
    &u = exp(&u);
  %end;
%mend _fc_back;

%macro arima_forecast(rx_data=work.rx_monthly, product='Drug A', region='West',
                      start_dt='01JAN2016'd, end_dt='31DEC2025'd, transform=none,
                      ma_window=12, holdout=12, metric=rmse, final_model=best,
                      ar_p=0, diff_d=1, ma_q=1, sar_p=0, sdiff_d=1, sma_q=1,
                      horizon=6, conf_level=95);
  %local t0 n n_gaps n_train n_bad alpha i n_cand n_conv rec_id rec_name fin_id
         fin_name fin_note msg ok last_month lb12 _first _last _usable _lbl _scale
         _p _d _q _sp _sd _sq _cc _cerr n_shock;
  %global _log;
  %let t0 = %sysfunc(datetime());
  /* Keyword values may arrive macro-quoted (SAShiny raw choices) */
  %let transform = %lowcase(%unquote(&transform));
  %let metric = %lowcase(%unquote(&metric));
  %let final_model = %lowcase(%unquote(&final_model));
  %let ok = 1;
  %let msg = ;
  %let alpha = %sysevalf((100 - &conf_level) / 100);
  %let _log = %eval(%lowcase(&transform) = log);
  %let _scale = ;
  %if &_log %then %let _scale = log;
  %let n_conv = 0;
  %let rec_id = ;
  %let _usable = 0;

  /*------------------------------------------------------------------------
    1. Data: select the series, aggregate to months, fill missing months
  ------------------------------------------------------------------------*/
  data work._raw;
    length shock_flag 8;
    set &rx_data;
    where product = &product and region = &region
      and month between &start_dt and &end_dt;
    month = intnx('month', month, 0, 'b');
    keep month prescriptions shock_flag;
  run;

  proc sql noprint;
    create table work._agg as
      select month, sum(prescriptions) as prescriptions,
             max(coalesce(shock_flag, 0)) as shock_flag
      from work._raw
      where not missing(month)
      group by month
      order by month;
    select count(*) into :n trimmed from work._agg;
  quit;

  %if &n = 0 %then %do;
    %let ok = 0;
    %let msg = No rows for product %sysfunc(dequote(&product)) and region %sysfunc(dequote(&region)) in the selected months.;
    %put ERROR: &msg;
    %goto status;
  %end;

  /* A complete monthly grid: missing months become missing values */
  proc sql noprint;
    select min(month), max(month) into :_first trimmed, :_last trimmed from work._agg;
  quit;
  data work._grid;
    format month monyy7.;
    do i = 0 to intck('month', &_first, &_last);
      month = intnx('month', &_first, i, 'b');
      output;
    end;
    drop i;
  run;
  data work.series;
    merge work._grid(in=g) work._agg;
    by month;
    if g;
    label month = 'Month' prescriptions = 'Prescriptions' shock_flag = 'Shock month';
  run;

  proc sql noprint;
    select count(*), sum(missing(prescriptions)), sum(prescriptions <= 0),
           sum(shock_flag = 1)
      into :n trimmed, :n_gaps trimmed, :n_bad trimmed, :n_shock trimmed
      from work.series;
  quit;
  %let last_month = %sysfunc(putn(&_last, monyy7.));

  %if &n < %eval(&holdout + 36) %then %do;
    %let ok = 0;
    %let msg = The series has &n months but at least %eval(&holdout + 36) are needed (the holdout plus 36 months to fit seasonal models).;
    %put ERROR: &msg;
    %goto status;
  %end;
  %if &_log and &n_bad > 0 %then %do;
    %let ok = 0;
    %let msg = The log transform needs positive values but &n_bad months are zero or negative.;
    %put ERROR: &msg;
    %goto status;
  %end;
  %if &n_gaps > 0 %then
    %put WARNING: &n_gaps month(s) have no data. PROC ARIMA treats them as missing values.;

  /* Model scale and trailing moving average */
  data work._model;
    set work.series;
    %if &_log %then %do; y = log(prescriptions); %end;
    %else %do; y = prescriptions; %end;
    t = _n_;
  run;
  proc expand data=work.series out=work._ma(keep=month moving_avg) method=none;
    id month;
    convert prescriptions = moving_avg / transformout=(movave &ma_window);
  run;
  data work.series;
    merge work.series work._ma;
    by month;
    shock_point = ifn(shock_flag = 1, prescriptions, .);
    label moving_avg = "&ma_window-month moving average" shock_point = 'Shock month';
    format moving_avg comma10.;
  run;

  /*------------------------------------------------------------------------
    2. Candidates: curated set, plus the custom orders when chosen
  ------------------------------------------------------------------------*/
  /* Orders as p d q P D Q: ARIMA(1,1,0), (0,1,1), (1,1,1) and five seasonal models */
  data work._cand;
    length id $8 spec $11;
    array o{6} p d q sp sd sq;
    do i = 1 to 8;
      id = cats('m', i);
      spec = scan('1 1 0 0 0 0|0 1 1 0 0 0|1 1 1 0 0 0|0 1 1 0 1 1|'
               || '1 1 0 0 1 1|1 1 1 0 1 1|1 0 0 0 1 1|2 1 0 1 1 0', i, '|');
      do k = 1 to 6;
        o{k} = input(scan(spec, k, ' '), 1.);
      end;
      output;
    end;
    keep id p d q sp sd sq;
  run;
  %if %lowcase(&final_model) = custom %then %do;
    data work._cand_c;
      length id $8;
      id = 'custom'; p = &ar_p; d = &diff_d; q = &ma_q; sp = &sar_p; sd = &sdiff_d; sq = &sma_q;
    run;
    proc append base=work._cand data=work._cand_c; run;
  %end;

  proc sql noprint;
    select count(*) into :n_cand trimmed from work._cand;
    %do i = 1 %to &n_cand;
      %local c_id&i c_p&i c_d&i c_q&i c_sp&i c_sd&i c_sq&i;
    %end;
    select id, p, d, q, sp, sd, sq
      into :c_id1-, :c_p1-, :c_d1-, :c_q1-, :c_sp1-, :c_sd1-, :c_sq1-
      from work._cand;
  quit;

  /*------------------------------------------------------------------------
    3. Holdout evaluation: fit on the training months, forecast the holdout
  ------------------------------------------------------------------------*/
  %let n_train = %eval(&n - &holdout);
  data work._train;
    set work._model(obs=&n_train);
  run;
  data work._hold;
    set work._model(firstobs=%eval(&n_train + 1));
    keep month prescriptions;
  run;

  proc datasets library=work nolist nowarn; delete model_comparison _hfc_all; quit;

  %do i = 1 %to &n_cand;
    %_fc_spec(&&c_p&i, &&c_d&i, &&c_q&i, &&c_sp&i, &&c_sd&i, &&c_sq&i)
    proc datasets library=work nolist nowarn; delete _stat _fc; quit;

    /* A failing candidate must not fail the run: its log goes to a temporary
       file, and its messages come back below as notes */
    %let _cc = &syscc;
    filename _fclog temp;
    proc printto log=_fclog new; run;
    proc arima data=work._train plots=none;
      identify var=y&_dif noprint;
      estimate &_ar &_ma &_int method=ml maxiter=100 outstat=work._stat noprint;
      forecast lead=&holdout id=month interval=month out=work._fc noprint;
    run;
    quit;
    proc printto; run;
    %let syscc = &_cc;

    %let _cerr = 0;
    data _null_;
      infile _fclog end=eof;
      input;
      length level $8 text $400;
      if _infile_ =: 'ERROR' or _infile_ =: 'WARNING' then do;
        n_err + (_infile_ =: 'ERROR');
        /* Lower-case level, so a wrapped log line never starts with ERROR or WARNING */
        level = lowcase(scan(_infile_, 1, ' :'));
        text = strip(substr(_infile_, index(_infile_, ':') + 1));
        put "NOTE: Candidate &&c_id&i &_name, " level +(-1) ': ' text;
      end;
      if eof then call symputx('_cerr', n_err);
    run;
    filename _fclog clear;

    %if &_cerr > 0 or not %sysfunc(exist(work._stat)) %then %do;
      data work._stat; length _STAT_ $8; _STAT_ = 'CONV'; _VALUE_ = 9; run;
    %end;
    %if &_cerr > 0 or not %sysfunc(exist(work._fc)) %then %do;
      data work._fc; set work._hold(obs=0 keep=month); forecast = .; std = .; l95 = .; u95 = .; run;
    %end;

    /* Holdout forecasts on the prescription scale */
    data work._hfc;
      merge work._hold(in=h) work._fc(keep=month forecast std l95 u95);
      by month;
      if h;
      length id $8 model $40;
      id = "&&c_id&i";
      model = "&_name";
      %_fc_back(forecast, std, l95, u95)
      err = prescriptions - forecast;
      keep id model month prescriptions forecast err;
    run;
    proc append base=work._hfc_all data=work._hfc; run;

    proc sql noprint;
      create table work._row as
        select "&&c_id&i" as id length=8,
               "&_name" as model length=40,
               &&c_p&i as p, &&c_d&i as d, &&c_q&i as q,
               &&c_sp&i as sp, &&c_sd&i as sd, &&c_sq&i as sq,
               (select _value_ from work._stat where _stat_ = 'CONV') = 0 as converged,
               (select _value_ from work._stat where _stat_ = 'AIC') as aic,
               (select _value_ from work._stat where _stat_ = 'SBC') as sbc,
               sqrt(mean(err**2)) as rmse,
               mean(abs(err)) as mae,
               sum(abs(err)) / sum(abs(prescriptions)) * 100 as wape,
               nmiss(forecast) as n_missing_fc
        from work._hfc;
    quit;
    proc append base=work.model_comparison data=work._row force; run;
  %end;

  /* A candidate counts only if it converged and forecast every holdout month */
  data work.model_comparison;
    set work.model_comparison;
    usable = (converged = 1 and n_missing_fc = 0);
    score = ifn(usable, &metric, .);
  run;

  proc sql noprint;
    select count(*) into :n_conv trimmed from work.model_comparison where usable;
    select id, model into :rec_id trimmed, :rec_name trimmed
      from work.model_comparison
      where usable and id ne 'custom'
      having score = min(score);
  quit;

  %if &n_conv = 0 or %length(&rec_id) = 0 %then %do;
    %let ok = 0;
    %let msg = No candidate model converged on this series.;
    %put ERROR: &msg;
    %goto status;
  %end;

  /* Final model: the recommendation, the custom orders or a named candidate */
  %let fin_note = ;
  %if %lowcase(&final_model) = best %then %let fin_id = &rec_id;
  %else %let fin_id = %lowcase(&final_model);
  proc sql noprint;
    select model, usable into :fin_name trimmed, :_usable trimmed
      from work.model_comparison where id = "&fin_id";
  quit;
  %if &_usable = 0 %then %do;
    %put WARNING: The chosen model &fin_name did not converge on the training months. Using the recommended model &rec_name instead.;
    %let fin_note = (&fin_name did not converge);
    %let fin_id = &rec_id;
    %let fin_name = &rec_name;
  %end;

  proc sort data=work.model_comparison; by descending usable score; run;
  data work.model_comparison;
    set work.model_comparison;
    length decision $32;
    if usable then _r + 1;
    rank = ifn(usable, _r, .);
    if not usable then decision = 'Not converged';
    else if id = "&rec_id" and id = "&fin_id" then decision = 'Recommended, final';
    else if id = "&rec_id" then decision = 'Recommended';
    else if id = "&fin_id" then decision = 'Final';
    label id = 'Id' model = 'Model' rank = 'Rank' converged = 'Converged'
          aic = 'AIC (train)' sbc = 'SBC (train)' rmse = 'Holdout RMSE'
          mae = 'Holdout MAE' wape = 'Holdout WAPE (%)' decision = 'Decision';
    format aic sbc 10.1 rmse mae comma10.1 wape 6.2 converged 1.;
    keep rank id model converged rmse mae wape aic sbc decision;
  run;
  data work.model_comparison;
    retain rank id model decision rmse mae wape aic sbc converged;
    set work.model_comparison;
  run;

  /* Holdout chart data: the last 36 months, with the final and recommended forecasts */
  data work._hplot;
    length series $60;
    set work.series(keep=month prescriptions firstobs=%sysfunc(max(1, %eval(&n - 35))))
        work._hfc_all(where=(id in ("&fin_id" "&rec_id")) in=f);
    if f then do;
      prescriptions = forecast;
      if id = "&fin_id" then series = catx(' ', 'Final:', model);
      else series = catx(' ', 'Recommended:', model);
    end;
    else series = 'Actual';
    keep month prescriptions series;
  run;
  proc sort data=work._hplot; by series month; run;

  /*------------------------------------------------------------------------
    4. Final model: refit on all months and forecast
  ------------------------------------------------------------------------*/
  proc sql noprint;
    select p, d, q, sp, sd, sq into :_p trimmed, :_d trimmed, :_q trimmed,
           :_sp trimmed, :_sd trimmed, :_sq trimmed
      from work._cand where id = "&fin_id";
  quit;
  %_fc_spec(&_p, &_d, &_q, &_sp, &_sd, &_sq)

  ods output ParameterEstimates=work._pe ChiSqAuto=work._wn;
  proc arima data=work._model plots=none;
    identify var=y&_dif nlag=24 outcov=work._cov noprint;
    estimate &_ar &_ma &_int method=ml outstat=work._fstat;
    forecast lead=&horizon id=month interval=month alpha=&alpha out=work._ff noprint;
  run;
  quit;
  /* PROC ARIMA names the limits after the level (L95/U95, L90/U90, ...) */
  data work._ff;
    set work._ff(rename=(l&conf_level=lcl u&conf_level=ucl));
  run;

  data work.estimates;
    set work._pe;
    label parameter = 'Parameter' estimate = 'Estimate' stderr = 'Std error'
          tvalue = 't value' probt = 'p value' lag = 'Lag';
    format estimate stderr 10.4 tvalue 8.2 probt pvalue6.4;
    keep parameter estimate stderr tvalue probt lag;
  run;

  data work.white_noise;
    set work._wn;
    length verdict $40;
    if probchisq > 0.05 then verdict = 'No significant autocorrelation';
    else verdict = 'Autocorrelation left in residuals';
    label tolags = 'To lag' chisq = 'Chi-square' df = 'DF' probchisq = 'p value'
          verdict = 'Verdict';
    format chisq 8.2 probchisq pvalue6.4;
    keep tolags chisq df probchisq verdict;
  run;
  proc sql noprint;
    select probchisq format=pvalue6.4 into :lb12 trimmed from work.white_noise where tolags = 12;
  quit;

  /* In-sample fit (one-step-ahead) and residuals on the model scale */
  data work.diagnostics;
    merge work._model(keep=month prescriptions in=m) work._ff(keep=month forecast std lcl ucl residual);
    by month;
    if m;
    fitted = forecast;
    %_fc_back(fitted, std, lcl, ucl)
    label month = 'Month' prescriptions = 'Actual' fitted = 'Fitted (one step ahead)'
          residual = "Residual (%sysfunc(ifc(&_log, log scale, prescriptions)))";
    format fitted comma10.;
    keep month prescriptions fitted residual;
  run;

  data work.forecast;
    set work._ff(firstobs=%eval(&n + 1) keep=month forecast std lcl ucl);
    %_fc_back(forecast, std, lcl, ucl)
    lower = lcl;
    upper = ucl;
    label month = 'Month' forecast = 'Forecast'
          lower = "Lower &conf_level% limit" upper = "Upper &conf_level% limit";
    format month monyy7. forecast lower upper comma10.;
    keep month forecast lower upper;
  run;

  /* ACF / PACF of the series as the final model differences it */
  data work._acf;
    set work._cov(where=(lag > 0));
    length measure $4;
    measure = 'ACF';  value = corr;     ci = 2 * stderr;      output;
    measure = 'PACF'; value = partcorr; ci = 2 / sqrt(n);     output;
    keep lag measure value ci;
  run;
  data work._acf; set work._acf; lo = -ci; run;

  /* Residual ACF */
  proc arima data=work.diagnostics plots=none;
    identify var=residual nlag=24 outcov=work._rcov noprint;
  run;
  quit;
  data work._racf;
    set work._rcov(where=(lag > 0));
    ci = 2 * stderr;
    lo = -ci;
    keep lag corr ci lo;
  run;

  /* History and forecast chart data: the last 48 months plus the forecast */
  data work._fplot;
    set work.diagnostics(firstobs=%sysfunc(max(1, %eval(&n - 47))) keep=month prescriptions fitted)
        work.forecast;
    format month monyy7.;
  run;

  /*------------------------------------------------------------------------
    5. Graphs, in the fixed order listed in the header
  ------------------------------------------------------------------------*/
  proc format;
    value _moy 1='Jan' 2='Feb' 3='Mar' 4='Apr' 5='May' 6='Jun'
               7='Jul' 8='Aug' 9='Sep' 10='Oct' 11='Nov' 12='Dec';
  run;

  ods graphics on / width=8in height=4in;
  %let _lbl = %sysfunc(dequote(&product)), %sysfunc(dequote(&region));

  title "1. Monthly prescriptions: &_lbl";
  proc sgplot data=work.series;
    series x=month y=prescriptions / legendlabel='Prescriptions' lineattrs=(thickness=1);
    series x=month y=moving_avg / legendlabel="&ma_window-month moving average" lineattrs=(thickness=2);
    %if &n_shock > 0 %then %do;
      scatter x=month y=shock_point / legendlabel='Shock month'
              markerattrs=(symbol=circlefilled size=8);
    %end;
    xaxis label='Month';
    yaxis label='Prescriptions' grid;
  run;

  data work._season;
    set work.series;
    moy = month(month);
    format moy _moy.;
  run;
  title "2. Seasonal profile by calendar month: &_lbl";
  proc sgplot data=work._season;
    vbox prescriptions / category=moy;
    xaxis label='Calendar month' discreteorder=unformatted;
    yaxis label='Prescriptions' grid;
  run;

  title "3. ACF and PACF of %sysfunc(compbl(&_scale prescriptions)), differencing &_dif";
  proc sgpanel data=work._acf;
    panelby measure / columns=2 novarname;
    band x=lag upper=ci lower=lo / transparency=0.7 legendlabel='Approx. 95% limits';
    needle x=lag y=value / baseline=0 markers legendlabel='Correlation';
    colaxis label='Lag (months)' values=(0 to 24 by 6);
    rowaxis label='Correlation';
  run;

  data work._cmp;
    set work.model_comparison;
    length group $32;
    group = coalescec(decision, 'Candidate');
  run;
  /* Fixed colours per decision, whatever order the groups appear in */
  data work._attr;
    length id $8 value $32 fillcolor linecolor $8;
    id = 'dec';
    linecolor = 'cx5A6470';
    value = 'Recommended, final'; fillcolor = 'cx1F5FA8'; output;
    value = 'Recommended';        fillcolor = 'cx1F5FA8'; output;
    value = 'Final';              fillcolor = 'cxE07B00'; output;
    value = 'Candidate';          fillcolor = 'cxB8C2CC'; output;
    value = 'Not converged';      fillcolor = 'cxE8A0A0'; output;
  run;
  title "4. Holdout %upcase(&metric) by candidate (last &holdout months)";
  proc sgplot data=work._cmp dattrmap=work._attr;
    hbar model / response=&metric group=group attrid=dec categoryorder=respasc datalabel;
    xaxis label="Holdout %upcase(&metric)" grid;
    yaxis display=(nolabel);
    keylegend / title='';
  run;

  title "5. Holdout forecasts versus actual";
  proc sgplot data=work._hplot;
    series x=month y=prescriptions / group=series markers lineattrs=(thickness=2);
    refline %sysfunc(intnx(month, &_last, -&holdout, e)) / axis=x label='Holdout starts' lineattrs=(pattern=dash);
    xaxis label='Month';
    yaxis label='Prescriptions' grid;
    keylegend / title='';
  run;

  ods graphics / width=8in height=3.2in;
  title "6. Residuals of &fin_name";
  proc sgplot data=work.diagnostics;
    needle x=month y=residual / baseline=0;
    refline 0 / axis=y;
    xaxis label='Month';
    yaxis label='Residual' grid;
  run;

  title "7. Residual ACF";
  proc sgplot data=work._racf;
    band x=lag upper=ci lower=lo / transparency=0.7 legendlabel='Approx. 95% limits';
    needle x=lag y=corr / baseline=0 markers legendlabel='Correlation';
    xaxis label='Lag (months)' values=(0 to 24 by 6);
    yaxis label='Correlation';
  run;

  title "8. Residual distribution";
  proc sgplot data=work.diagnostics;
    histogram residual;
    density residual / type=normal;
    xaxis label='Residual';
  run;

  ods graphics / width=8in height=4.5in;
  title "9. &_lbl: &horizon-month forecast with &fin_name";
  proc sgplot data=work._fplot;
    band x=month upper=upper lower=lower / transparency=0.6 legendlabel="&conf_level% prediction interval";
    series x=month y=prescriptions / legendlabel='Actual' lineattrs=(thickness=2);
    series x=month y=fitted / legendlabel='Fitted' lineattrs=(pattern=dash);
    series x=month y=forecast / legendlabel='Forecast' markers lineattrs=(thickness=2);
    refline &_last / axis=x lineattrs=(pattern=dot);
    xaxis label='Month';
    yaxis label='Prescriptions' grid;
  run;
  title;
  ods graphics / reset;

  /*------------------------------------------------------------------------
    6. Run status
  ------------------------------------------------------------------------*/
%status:
  data work.run_status;
    length item $40 value $120;
    label item = 'Item' value = 'Value';
    item = 'Status';    value = ifc(&ok, 'Completed', 'Failed'); output;
    %if not &ok %then %do;
      item = 'Message'; value = "&msg"; output;
    %end;
    item = 'Product, region'; value = catx(', ', &product, &region); output;
    %if &ok %then %do;
      item = 'Months used';       value = catx(' ', &n, 'months, to', "&last_month"); output;
      item = 'Missing months';    value = put(&n_gaps, 8. -l); output;
      item = 'Transform';         value = "%lowcase(&transform)"; output;
      item = 'Training / holdout'; value = catx(' ', &n_train, 'months /', &holdout, 'months'); output;
      item = 'Candidates fitted'; value = catx(' ', &n_cand, 'fitted,', &n_conv, 'usable'); output;
      item = 'Selection metric';  value = "Holdout %upcase(&metric)"; output;
      item = 'Recommended model'; value = "&rec_name"; output;
      item = 'Final model';       value = strip("&fin_name &fin_note"); output;
      item = 'Forecast';          value = catx(' ', &horizon, 'months at', "&conf_level%"); output;
      item = 'Ljung-Box p (lag 12)'; value = "&lb12"; output;
    %end;
  run;
  /* Timing goes to the log, so the same inputs always give identical tables */
  %put NOTE: arima_forecast finished in %sysfunc(putn(%sysevalf(%sysfunc(datetime()) - &t0), 8.1)) seconds.;

  proc datasets library=work nolist nowarn;
    delete _raw _agg _grid _ma _model _cand _cand_c _train _hold _stat _fc _hfc
           _hfc_all _row _hplot _pe _wn _fstat _ff _cov _acf _rcov _racf _fplot
           _season _cmp _attr;
  quit;
%mend arima_forecast;
