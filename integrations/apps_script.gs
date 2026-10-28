/**
 * AI Store Robot -> Google Sheets.
 * Extensions -> Apps Script in your Google Sheet, paste this, set TOKEN,
 * Deploy -> New deployment -> Web app (execute as Me, access: Anyone). Copy the URL
 * into config.json "sheets_webhook_url" and the TOKEN into "sheets_token".
 *
 * One tab per row type is created automatically: bills, khata, payments, stock, visits.
 */
var TOKEN = "change-me";

function doPost(e) {
  var row;
  try { row = JSON.parse(e.postData.contents); } catch (err) { return reply({ error: "bad json" }); }
  if (TOKEN && row.token !== TOKEN) return reply({ error: "bad token" });
  delete row.token;
  var type = String(row.type || "events");
  delete row.type;
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(type) || ss.insertSheet(type);
  var keys = Object.keys(row);
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(keys);
    sheet.setFrozenRows(1);
  } else {
    var header = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    var missing = keys.filter(function (k) { return header.indexOf(k) < 0; });
    if (missing.length) {
      sheet.getRange(1, header.length + 1, 1, missing.length).setValues([missing]);
      header = header.concat(missing);
    }
    keys = header;
  }
  sheet.appendRow(keys.map(function (k) { return row[k] === undefined ? "" : row[k]; }));
  return reply({ status: "ok" });
}

function doGet() { return reply({ status: "ok", hint: "POST JSON rows here" }); }

function reply(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
