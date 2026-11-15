import asyncio
import unittest
from unittest.mock import patch

from jsonschema import validate

import molit_mcp as m


class DetailTests(unittest.TestCase):
    def test_legacy_inputs_keep_single_or_batch_shape(self):
        with patch.object(m, '_detail_one', side_effect=lambda u: {'url': u}):
            for value in ('1', ['1']):
                self.assertEqual(m.get_detail(url=value)['url'], '1')
            for value in (['1', '2'], '["1", "2"]', '1,2'):
                self.assertEqual(m.get_detail(url=value)['count'], 2)

    def test_urls_always_returns_batch(self):
        with patch.object(m, '_detail_one', return_value={'url': '1'}):
            self.assertEqual(m.get_detail(urls=['1']), {'count': 1, 'items': [{'url': '1'}]})

    def test_invalid_arguments_do_not_fetch(self):
        with patch.object(m, '_detail_one') as fetch:
            for args in ({}, {'url': ''}, {'urls': []}, {'url': '1', 'urls': ['2']}):
                self.assertIn('error', m.get_detail(**args))
            fetch.assert_not_called()

    def test_batch_limit_and_partial_failure(self):
        def fetch(u):
            if u == '2':
                raise RuntimeError('temporary failure')
            return {'url': u}
        with patch.object(m, '_detail_one', side_effect=fetch) as mock:
            result = m.get_detail(urls=[str(i) for i in range(12)])
        self.assertEqual(mock.call_count, 10)
        self.assertEqual(result['count'], 10)
        self.assertIn('notice', result)
        self.assertIn('error', result['items'][2])
        self.assertEqual(result['items'][3]['url'], '3')

    def test_related_kinds_and_candidate_relationship(self):
        rows = [
            {'similrResourceSeq': 1, 'type': 'dataset', 'simildegerPt': 100},
            {'similrResourceSeq': 2, 'type': 'dataset', 'simildegerPt': '100.0'},
            {'similrResourceSeq': 3, 'type': 'dataservice', 'simildegerPt': 75},
            {'similrResourceSeq': 4, 'title': 'API 정보', 'simildegerPt': None},
            {'similrResourceSeq': 5, 'title': '문자정보 제공이력(FILE)', 'simildegerPt': 100,
             'resourceType': '개방 데이터', 'resourceTypeSeq': 4},
        ]
        related = m._related({'simildegers': rows}, '1')
        self.assertEqual(len(related), 4)
        self.assertEqual([r['kind'] for r in related], ['파일형', 'Open API형', '미확인', '파일형'])
        self.assertIn('추정', related[3]['kind_source'])
        self.assertIn('후보', related[0]['relationship'])
        self.assertEqual(related[1]['relationship'], '유사 데이터')

    def test_detail_includes_verification_guidance(self):
        fixture = {'resource': {'title': 'Example', 'type': 'dataset'},
                   'simildegers': [{'similrResourceSeq': '2', 'simildegerPt': 100}]}
        with patch.object(m, '_detail_call', return_value=fixture):
            detail = m.get_detail(url='1')
        self.assertIn('related_hint', detail)
        self.assertIn('batch_hint', detail)

    def test_mcp_schema_accepts_legacy_and_batch_arguments(self):
        async def check():
            tool = next(t for t in await m.mcp.list_tools() if t.name == 'get_detail')
            schema = tool.model_dump(by_alias=True)['inputSchema']
            self.assertIn('urls', schema['properties'])
            self.assertIn('url', schema['properties'])
            self.assertFalse(schema.get('required'))
            for args in ({'url': '1'}, {'url': ['1', '2']}, {'urls': ['1', '2']}):
                validate(args, schema)
        asyncio.run(check())


if __name__ == '__main__':
    unittest.main()
