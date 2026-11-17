import pytest
from scripts.import_student_life_catalog import allowed_source

@pytest.mark.parametrize("row,existing,allowed",[
 ({"source_url":"https://official.example/new"},"https://official.example/new",True),
 ({"source_url":"https://official.example/new"},None,False),
 ({"source_url":"https://official.example/new"},"https://other.example/guide",False),
 ({"source_url":"https://official.example/new","previous_source_url":"https://official.example/old"},"https://official.example/old",True),
 ({"source_url":"https://official.example/new","previous_source_url":"https://official.example/old"},"https://custom.example/guide",False),
 ({"source_url":"https://official.example/new","previous_source_url":None},None,False),
 ({"source_url":"https://official.example/new","previous_source_url":""},"",False),
])
def test_only_the_explicit_reviewed_source_can_be_migrated(row,existing,allowed):
 assert allowed_source(row,existing) is allowed
