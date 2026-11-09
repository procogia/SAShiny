/*----------------------------------------------------------------------------
  Program : cash_aggregation_tuning.sas
  Purpose : AML scenario "Large cash aggregation" with above/below-the-line
            threshold sensitivity. A customer alerts when the sum of their
            cash deposits over a rolling look-back window reaches THRESHOLD.
  Inputs  : TXN_DATA       transaction dataset (CUSTOMER_ID, SEGMENT, TXN_TYPE,
                           TXN_DATE, AMOUNT, SAR_FLAG)
            SEGMENTS       quoted list of customer segments
            THRESHOLD      alert threshold (currency units)
            LOOKBACK_DAYS  rolling window length in days
            START_DT       first transaction date, SAS date literal
            END_DT         last transaction date, SAS date literal
  Outputs : WORK.ALERTS, WORK.ATL_BTL, one ODS graph, two listings
  Notes   : Runs standalone with the defaults below; requires SAS 9.4M5+.
            SAR_FLAG marks customers with a prior SAR and is used only to
            estimate how many known cases each threshold would catch.
----------------------------------------------------------------------------*/

%if not %symexist(txn_data)      %then %do; %let txn_data      = work.transactions; %end;
%if not %symexist(segments)      %then %do; %let segments      = 'Retail' 'SME' 'Corporate'; %end;
%if not %symexist(threshold)     %then %do; %let threshold     = 10000; %end;
%if not %symexist(lookback_days) %then %do; %let lookback_days = 30; %end;
%if not %symexist(start_dt)      %then %do; %let start_dt      = '01JAN2026'd; %end;
%if not %symexist(end_dt)        %then %do; %let end_dt        = '30JUN2026'd; %end;

/* Cash deposits in scope */
data work._cash;
  set &txn_data;
  where txn_type = 'CASH_DEPOSIT'
    and segment in (&segments)
    and txn_date between &start_dt and &end_dt;
run;

proc sql noprint;
  /* One row per customer and deposit day */
  create table work._days as
    select distinct customer_id, txn_date
    from work._cash;

  /* Rolling sum of deposits over the look-back window ending on each day */
  create table work._rolling as
    select d.customer_id, d.txn_date, sum(c.amount) as rolling_amt
    from work._days as d
         inner join work._cash as c
           on  c.customer_id = d.customer_id
           and c.txn_date between d.txn_date - &lookback_days + 1 and d.txn_date
    group by d.customer_id, d.txn_date;

  /* Customer attributes and peak rolling amount */
  create table work._peak as
    select r.customer_id, a.segment, a.sar_flag, max(r.rolling_amt) as peak_amt
    from work._rolling as r
         inner join (select customer_id, max(segment) as segment, max(sar_flag) as sar_flag
                     from work._cash group by customer_id) as a
           on r.customer_id = a.customer_id
    group by r.customer_id, a.segment, a.sar_flag;

  /* Alerts at the current threshold */
  create table work.alerts as
    select customer_id label='Customer',
           segment label='Segment',
           peak_amt label='Peak rolling cash deposits' format=comma14.2,
           sar_flag label='Prior SAR'
    from work._peak
    where peak_amt >= &threshold
    order by peak_amt desc;

  select count(*) into :n_sar_total trimmed from work._peak where sar_flag = 1;
quit;

/* Threshold grid: 50% to 150% of the current threshold */
data work._grid;
  do pct_of_current = 50 to 150 by 10;
    test_threshold = round(&threshold * pct_of_current / 100, 1);
    output;
  end;
run;

proc sql;
  create table work.atl_btl as
    select g.pct_of_current label='% of current threshold',
           g.test_threshold label='Threshold' format=comma12.,
           sum(p.peak_amt >= g.test_threshold) as alerts label='Alerts',
           sum(p.peak_amt >= g.test_threshold and p.sar_flag = 1) as sar_caught label='Prior-SAR customers alerted',
           case when calculated alerts > 0
                then calculated sar_caught / calculated alerts
                else . end as hit_rate label='Hit rate' format=percent8.1,
           case when &n_sar_total > 0
                then calculated sar_caught / &n_sar_total
                else . end as sar_recall label='Prior-SAR recall' format=percent8.1
    from work._grid as g, work._peak as p
    group by g.pct_of_current, g.test_threshold
    order by g.pct_of_current;
quit;

ods graphics / width=8in height=4.5in;

title 'Above/below-the-line analysis: alert volume and hit rate by threshold';
proc sgplot data=work.atl_btl;
  vbar test_threshold / response=alerts fillattrs=(transparency=0.4) legendlabel='Alerts';
  vline test_threshold / response=hit_rate y2axis markers lineattrs=(thickness=2) legendlabel='Hit rate';
  yaxis label='Alerts';
  y2axis label='Hit rate' min=0 max=1;
  xaxis label='Threshold' fitpolicy=rotate;
run;

title 'Threshold sensitivity';
proc print data=work.atl_btl noobs label;
run;

title 'Alerted customers at the current threshold';
proc print data=work.alerts(obs=50) noobs label;
run;
title;

proc datasets library=work nolist nowarn;
  delete _cash _days _rolling _peak _grid;
quit;
%symdel n_sar_total / nowarn;
