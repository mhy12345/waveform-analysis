SHELL=bash
jinpDir=dataset/jinp
xiaoPp=test/xiaopeip

xtest=xtest
xtestPl=99
xtestseq=$(shell seq 0 ${xtestPl})

xall: $(xtest)/hist-x.pdf $(xtest)/record-x.csv
$(xtest)/record-x.csv: $(xtest)/distrecord/distrecord-x.h5
	mkdir -p $(dir $@)
	python3 test/csv_dist.py $^ -o $@
$(xtest)/hist-x.pdf: $(xtest)/distrecord/distrecord-x.h5
	python3 test/draw_dist.py $^ --wthres 20 -o $@
$(xtest)/distrecord/distrecord-x.h5: $(xtest)/ztraining-x.h5 $(xtest)/submission/submission-x.h5
	mkdir -p $(dir $@)
	python3 test/test_dist.py $(word 2,$^) --ref $< -o $@ > $@.log 2>&1
$(xtest)/submission/submission-x.h5: $(xtest)/submission/total-x.h5
	mkdir -p $(dir $@)
	python3 $(xiaoPp)/adjust.py $^ -o $@
$(xtest)/submission/total-x.h5: $(xtestseq:%=$(xtest)/unadjusted/unadjusted-x-%.h5)
	mkdir -p $(dir $@)
	python3 $(xiaoPp)/integrate.py $^ --num ${xtestPl} -o $@
$(xtest)/unadjusted/unadjusted-x-%.h5: $(xtest)/ztraining-x.h5 $(xiaoPp)/averspe.h5
	mkdir -p $(dir $@)
	python3 $(xiaoPp)/finalfit.py $< --ref $(word 2,$^) --num ${xtestPl} -o $@
$(xtest)/ztraining-x.h5: $(jinpDir)/ztraining-1.h5
	mkdir -p $(dir $@)
	python3 test/cut_data.py $^ -o $@ -a -1 -b 10000
$(xiaoPp)/averspe.h5: $(jinpDir)/ztraining-0.h5
	python3 test/spe_get.py $^ -o $@ --num 10000 --len 80
