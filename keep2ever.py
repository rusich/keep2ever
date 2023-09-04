""" keep2ever """
import io
import argparse
import re
import json
import base64
import html
from datetime import datetime
from zipfile import ZipFile
import magic
from PIL import Image
from hashlib import md5
from bleach import linkify

NOTEBOOK_HEADER = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE en-export SYSTEM "http://xml.evernote.com/pub/evernote-export3.dtd">
<en-export export-date="20201201T084211Z" application="Evernote" version="10.1.7">
"""
NOTEBOOK_FOOTER = "</en-export>"
NOTE_TEMPLATE = """<note>
    <title>{note_title}</title>
    <created>{note_created}</created>
    <updated>{note_updated}</updated>
    <note-attributes>
    </note-attributes>
    <content>
      <![CDATA[<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd"><en-note>
{note_content}
</en-note>      ]]>
    </content>
{note_tags}
{note_resource}
  </note>
"""


def parse_args():
    """ Parses CLI arguments """
    parser = argparse.ArgumentParser(
        description='Export Google Keep to Evernote')

    parser.add_argument('ImportFile', type=str,
                        help='Google takeout export file(.zip)')
    parser.add_argument("ExportFile", help='Output file',
                        nargs='?', default="")
    return parser.parse_args()


def evernote_datetime(timestamp):
    """ Convert unix timestamp to Evernote datetime format """
    dtfts = datetime.fromtimestamp(timestamp / 1000000)
    return dtfts.strftime("%Y%m%dT%H%M%SZ")


def evernote_resources(json_note, zip_file):
    """ Generates "<resource>" note section from file"""
    mime = magic.Magic(mime=True)
    resources = ""
    en_media_tags = ""

    for res in json_note['attachments']:
        res_path = 'Takeout/Keep/' + res['filePath']
        try:
            res_data = zip_file.read(res_path)
        except KeyError as ex:
            print(ex)
            continue

        mimetype = mime.from_buffer(res_data)
        resources += "<resource><data encoding=\"base64\">"
        en_media_tags += f'<en-media alt="" type="{mimetype}" hash="{md5(res_data).hexdigest()}"/>'
        data_b64 = base64.b64encode(res_data)

        resources += data_b64.decode()
        resources += f"</data><mime>{mimetype}</mime>"

        if 'image' in resources:
            try:
                img = Image.open(io.BytesIO(res_data))
                resources += f"<width>{img.width}</width>"
                resources += f"<height>{img.height}</height>"
            except Exception as error:
                print(res_path, error)

        resources += "<resource-attributes><file-name>"
        resources += res['filePath']
        resources += "</file-name></resource-attributes>"
        resources += "</resource>"

    return resources, en_media_tags


def evernote_tags(json_note):
    tags = ""
    for label in json_note.get('labels', []):
        tags += f"<tag>{html.escape(label['name'])}</tag>\n"
    if json_note['isArchived']:
        tags += "<tag>Archived</tag>"
    if json_note['isPinned']:
        tags += "<tag>Pinned</tag>"
    return tags


def export_notes(impmort_file, export_to_file):
    """ Export Google Keep notes (Keepout archive) to Evernote notepad file (.enex) """
    export_filename = "GoogleKeep"
    if export_to_file != "":
        export_filename = export_to_file

    if not export_filename.endswith(".enex"):
        export_filename = export_filename + ".enex"

    try:
        notebook_file = open(export_filename, "w")
        notebook_file.write(NOTEBOOK_HEADER)
        json_files_re = r'^Takeout\/Keep\/.*\.json'
        with ZipFile(impmort_file, 'r') as zip_file:
            for file in zip_file.namelist():
                if re.match(json_files_re, file):
                    json_note = json.loads(zip_file.read(file))
                    if json_note['isTrashed']:
                        continue
                    content = ""
                    evernote_dt = evernote_datetime(
                        json_note['userEditedTimestampUsec'])
                    if 'textContent' in json_note:
                        content = html.escape(linkify(json_note['textContent'], []))
                        content = content.replace('\n', '<br/>\n')
                    elif 'listContent' in json_note:
                        for item in json_note['listContent']:
                            checked = str(item['isChecked']).lower()
                            content += f'<div><en-todo checked="{checked}"/>{html.escape(linkify(item["text"], []))}</div>'

                    evernote_resource = ''

                    if 'attachments' in json_note:
                        evernote_resource, en_media_tags = evernote_resources(json_note, zip_file)
                        content += en_media_tags

                    tags = evernote_tags(json_note)

                    template_values = {
                        'note_title': html.escape(json_note['title']),
                        'note_created': evernote_dt,
                        'note_updated': evernote_dt,
                        'note_content': content,
                        'note_tags': tags,
                        'note_resource': evernote_resource,
                    }

                    notebook_file.write(
                        NOTE_TEMPLATE.format(**template_values))

        notebook_file.write(NOTEBOOK_FOOTER)
        notebook_file.close()
    except Exception as ex:
        print(ex)


if __name__ == "__main__":
    ARGS = parse_args()
    export_notes(ARGS.ImportFile, ARGS.ExportFile)
