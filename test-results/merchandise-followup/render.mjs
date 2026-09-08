import fs from 'node:fs/promises';
import {FileBlob, SpreadsheetFile} from '@oai/artifact-tool';
const root = 'C:/Users/Ermolenko.i/PycharmProjects/KANZLER_AI/test-results';
const file = `${root}/real-merchandise/KANZLER_Контроль_ассортимента_2026-09-06.xlsx`;
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(file));
console.log((await wb.inspect({kind:'region',sheetId:'Сводка',range:'A5:D13',maxChars:2000,tableMaxRows:9,tableMaxCols:4})).ndjson);
const ranges = [
 ['Сводка','A1:D15','summary'],['Категории','A1:J7','categories'],
 ['Артикулы','A1:H7','articles-input'],['Артикулы','AC1:AL7','articles-decisions'],
 ['План по неделям','A1:H7','weekly'],['Ценовые решения','A1:K7','prices'],
 ['Вторая волна','A1:G7','second'],['Действия','A1:H7','actions'],
 ['Качество данных','A1:E8','quality'],['План по месяцам','A1:G8','monthly'],
 ['История','A1:C7','history'],['Методика','A1:B8','methodology']];
for (const [sheetName,range,name] of ranges) {
 const blob = await wb.render({sheetName,range,scale:1.5,format:'png'});
 await fs.writeFile(`${root}/merchandise-followup/${name}.png`,new Uint8Array(await blob.arrayBuffer()));
 console.log(name);
}
