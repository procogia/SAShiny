/* Replay fixture program (spec section 6.6 (a)): one row holding the case number. */
data work.out;
  case = &case;
run;
