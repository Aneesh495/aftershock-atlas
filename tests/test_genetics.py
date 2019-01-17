from dataclasses import replace

import pytest

from aftershock.genetics import Association, align


def test_effect_allele_sign_and_build():
    a = Association("1", 100, "A", "C", .2, .1, .04, .2, 1000, 2000)
    assert align(a, a) == (.2, "exact")
    assert align(a, replace(a, reference="C", effect="A")) == (-.2, "swapped_effect")
    assert align(a, replace(a, reference="T", effect="G")) == (.2, "strand_complement")
    with pytest.raises(ValueError, match="build"):
        align(a, replace(a, build="GRCh37"))


def test_ambiguous_near_half_frequency_excluded():
    a = Association("1", 100, "A", "T", .2, .1, .04, .49, 1000, 2000)
    assert align(a, a) == (None, "ambiguous_strand")
