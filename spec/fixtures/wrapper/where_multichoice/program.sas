data work.t;
  set sashelp.cars;
  where origin in (&ORIGINS) and msrp >= &MIN_MSRP;
run;
