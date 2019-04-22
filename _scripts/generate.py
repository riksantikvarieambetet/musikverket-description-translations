from pywikibot.pagegenerators import CategorizedPageGenerator
from pywikibot import Site, Category
from dataskakare import GoogleTranslate
import mwparserfromhell
import hashlib
import uuid
import json

site = Site('commons', 'commons')
cat = Category(site, 'Category:Media_contributed_by_the_Swedish_Performing_Arts_Agency:_2019-03')
translate = GoogleTranslate(input('google service account file:'))

def thumb_from_title(title):
    safe_title = title.encode('utf-8')
    md5_title = hashlib.md5(safe_title).hexdigest()

    return 'https://upload.wikimedia.org/wikipedia/commons/thumb/{}/{}/{}/500px-{}.jpg'.format(md5_title[:1], md5_title[:2], title, title)

final_pages = list()
for page in CategorizedPageGenerator(cat, recurse=False, namespaces=6):
    wikicode = mwparserfromhell.parse(page.text)

    template_to_parse = False
    for template in wikicode.filter_templates():
        if template.name.matches('Musikverket-image'):
            template_to_parse = template

    if not template_to_parse:
        print('failed to find given template')
        continue

    page_data = {}

    page_data['media_id'] = '{}'.format(page.pageid)
    page_data['local_id'] = mwparserfromhell.parse(template_to_parse).filter_templates()[0].get('ID').value.lstrip()
    page_data['title'] = page.title(page.titleWithoutNamespace())
    page_data['thumbnail'] = thumb_from_title(page.titleForFilename().split('_', 1)[1])

    if '{{en' in mwparserfromhell.parse(template_to_parse).filter_templates()[0].get('description').value:
        continue

    page_data['desc'] = str(mwparserfromhell.parse(template_to_parse).filter_templates()[0].get('description').value)
    page_data['auto_desc'] = translate.translate(page_data['desc'], 'sv')

    print(page_data)
    with open('jsonfiles/{}.json'.format(str(uuid.uuid4())), 'w') as outfile:
        json.dump(page_data, outfile)
