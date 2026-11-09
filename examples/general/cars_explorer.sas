/*----------------------------------------------------------------------------
  Program : cars_explorer.sas
  Purpose : Summarise car prices and fuel economy from SASHELP.CARS.
  Inputs  : ORIGINS     quoted list of origins, e.g. 'Asia' 'USA'
            TYPES       quoted list of vehicle types
            MIN_MSRP    minimum MSRP (USD)
  Outputs : WORK.CARS_FILTERED, WORK.CARS_STATS, two ODS graphs, one listing
  Notes   : Runs standalone with the defaults below. SAShiny sets the macro
            variables before the program runs, so the defaults are skipped.
            Requires SAS 9.4M5+ (open-code %IF).
----------------------------------------------------------------------------*/

%if not %symexist(origins)  %then %do; %let origins  = 'Asia' 'Europe' 'USA'; %end;
%if not %symexist(types)    %then %do; %let types    = 'Sedan' 'SUV' 'Sports' 'Truck' 'Wagon' 'Hybrid'; %end;
%if not %symexist(min_msrp) %then %do; %let min_msrp = 0; %end;

data work.cars_filtered;
  set sashelp.cars;
  where origin in (&origins) and type in (&types) and msrp >= &min_msrp;
run;

proc means data=work.cars_filtered noprint nway;
  class origin type;
  var msrp mpg_city;
  output out=work.cars_stats(drop=_type_ rename=(_freq_=n_models))
         mean(msrp mpg_city)=mean_msrp mean_mpg_city
         median(msrp)=median_msrp;
run;

data work.cars_stats;
  set work.cars_stats;
  format mean_msrp median_msrp dollar10. mean_mpg_city 5.1;
  label n_models      = 'Models'
        mean_msrp     = 'Mean MSRP'
        median_msrp   = 'Median MSRP'
        mean_mpg_city = 'Mean city MPG';
run;

ods graphics / width=7in height=4.5in;

title 'MSRP versus city fuel economy';
proc sgplot data=work.cars_filtered;
  scatter x=mpg_city y=msrp / group=origin transparency=0.3 markerattrs=(symbol=circlefilled);
  xaxis label='City MPG';
  yaxis label='MSRP (USD)';
run;

title 'Mean MSRP by vehicle type and origin';
proc sgplot data=work.cars_stats;
  vbar type / response=mean_msrp group=origin groupdisplay=cluster;
  yaxis label='Mean MSRP (USD)';
  xaxis display=(nolabel);
run;

title 'Summary by origin and type';
proc print data=work.cars_stats noobs label;
  var origin type n_models mean_msrp median_msrp mean_mpg_city;
run;
title;
