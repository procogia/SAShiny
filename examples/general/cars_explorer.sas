/*----------------------------------------------------------------------------
  Program : cars_explorer.sas
  Purpose : Summarise car prices and fuel economy from SASHELP.CARS.
  Inputs  : ORIGINS     quoted list of origins, e.g. 'Asia' 'USA'
            TYPES       quoted list of vehicle types
            MIN_MSRP    minimum MSRP (USD)
  Outputs : WORK.CARS_FILTERED, WORK.CARS_STATS, two ODS graphs, one listing
  Notes   : Runs standalone with the defaults below. SAShiny sets the macro
            variables before the program runs, so the defaults are skipped.
            Runs on any SAS 9.4 release or SAS Viya.
----------------------------------------------------------------------------*/

/* Standalone defaults. The guard runs inside a macro so the program works on
   every SAS 9.4 release (open-code %IF needs 9.4M5+). */
%macro _default(_name, _value);
  %if not %symexist(&_name) %then %do;
    %global &_name;
    %let &_name = &_value;
  %end;
%mend _default;

%_default(origins, 'Asia' 'Europe' 'USA')
%_default(types, 'Sedan' 'SUV' 'Sports' 'Truck' 'Wagon' 'Hybrid')
%_default(min_msrp, 0)

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
