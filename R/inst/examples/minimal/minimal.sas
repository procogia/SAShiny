/* A minimal program for the SAShiny examples: prints SASHELP.CLASS. */
proc print data=sashelp.class(obs=&n_rows);
run;
