/* SAShiny 1 reset */
proc datasets library=work kill nolist nowarn;
quit;
%symdel MIN_MSRP ORIGINS N_ORIGINS / nowarn;
