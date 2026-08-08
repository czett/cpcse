from flask import Flask, render_template, redirect, request, url_for, send_from_directory, session, send_file
import os
import os.path as op
import time
import uuid
from rdkit import Chem
from rdkit.Chem import Draw
from rdkit.Chem.Draw import rdMolDraw2D
import base64
import string
import random

def del_old_files(base_dir, days=2):
    """Delete files older than `days` from `base_dir`."""
    now = time.time()
    for f in os.listdir(base_dir):
        full_path = op.join(base_dir, f)
        print(full_path)
        if op.isfile(full_path) and full_path.endswith(".txt"):
            if os.stat(full_path).st_mtime < (now - days * 86400):
                os.remove(full_path)

def check_files():
    files = os.listdir("static/tmp")

    for file in files:
        filepath = os.path.join("tmp", file)

        if os.path.isfile(filepath):
            stats = os.stat(filepath)
            creation = stats.st_ctime
            now = time.time()
            delta = int(now - creation)

            if delta > 600:
                os.remove(filepath)
            #else:
            #    print(f"The file {file} was created {delta} seconds ago.")

def gen_name(len:int):
    return "".join(random.choice(string.ascii_lowercase) for i in range (len))

def write_data(data, fname):
    for row in data:
        row.pop(4)

    with open(f"/home/CPCSE/mysite/static/tmp/{fname}.txt", "w") as f:
        for row in data:
            f.write("|".join(map(str, row)) + "\n")
        # for row in data:
        #     row = row.pop(4)
        #     f.write("|".join(map(str, row)) + "\n")

        # for substance in data:
        #     substance.pop(4)
        #     f.write("|".join(str(substance)) + "\n")

def smiletob64(smile : str) -> str:
    mol = Chem.MolFromSmiles(smile)
    drawer = rdMolDraw2D.MolDraw2DCairo(500, 500)
    drawer.SetFontSize(10)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()

    text = drawer.GetDrawingText()

    return base64.b64encode(text).decode('utf8')

def remove_img(data):
    #return data
    clean_list = []

    for index, item in enumerate(data):
        if index == 0:
            cleaned_item = item
        else:
            cleaned_item = item
            cleaned_item.pop(4)

        clean_list.append(cleaned_item)
        clean = tuple(clean_list)

    return clean

#App starts here

app = Flask(__name__)
app.secret_key = "4uYSoZQvHAJsUrjA9QmDGXQVzVW2ABVy"
max_search_count = 1000

app.config['UPLOAD_FOLDER'] = "/home/CPCSE/mysite/static/tmp/"

#coming soon block:
#@app.route("/")
#@app.route("/search")
#def block():
#    return render_template("comingsoon.html")

@app.route("/")
def landing():
    try:
        counter = session["count"]
        return render_template("search.html")
    except:
        return redirect("/setup")

@app.route("/search", methods=["POST"])
def search():
    start = time.time()
    #try:
    #Get input from HTML form
    inp = request.form["nm"]

    if inp == "":
        return redirect("/error")

    #Block page/Update count
    counter = session["count"]
    if counter[1] >= max_search_count:
        #Render template with error
        return render_template("main.html", max_reached=True)

    if counter[0] != time.strftime("%Y-%m-%d"):
        date_string = time.strftime("%Y-%m-%d")
        session["count"] = [date_string, 0]
    else:
        counter[1] = counter[1] + 1
        session["count"] = counter

    filename = "2612.txt"
    delimiter = "|"

    with open(f"/home/CPCSE/mysite/{filename}", "r", encoding="latin-1") as file:
        raw_content = file.readlines()
        content = []

        for index, item in enumerate(raw_content):
            if index == 0:
                legend = raw_content[index].split(delimiter)
                legend.insert(4, "Structure")
                raw_content.pop(index)
            else:
                temp = raw_content[index].split(delimiter)
                content.append(temp)

    def find(query):
        output = []
        for index, line in enumerate(content):
            if query.lower() in line[0].lower() or query.lower() in line[1].lower():
                modified_line = line.copy()  # Create a copy of the line
                modified_line.insert(4, smiletob64(line[1]))  # Insert Base64 into the copy
                #return smiletob64(line[1])

                for i in range(len(modified_line)):
                    try:
                        modified_line[i] = float(modified_line[i])
                    except (ValueError, TypeError):
                        pass #unfortunate :(

                output.append(modified_line)

        output = sorted(output, key=lambda x: (x[2], x[3])) #Sorting by Batch No (index=2) first, then concentration
        output.insert(0, legend)
        return output if len(output) > 0 else None

    if len(find(inp)) <= 1:
        return redirect("/error")

    #app_dir = op.dirname(__file__)

    #uuid_str = str(uuid.uuid4()).split("-")[0]
    #tmpfile = f"cluster_biosims_{uuid_str}.txt"

    #write_data(remove_img(find(inp)), op.join(app_dir, "tmp", tmpfile))

    #tmpfile_url = url_for("download", fname=tmpfile)

    # Clean up old files:
    #tmp_dir = op.join(app_dir, "tmp")
    #del_old_files(tmp_dir, days=2)
    #Render template with the output of function find(inp)
    output = find(inp)
    output[0].insert(4, "Structure")
    filen = gen_name(24)
    write_data(find(inp), filen)
    end = time.time()
    # slow - two function calls, fix when possible
    return render_template("main.html", output=output, counter=len(output),tmpfile_url="", max_reached=False, results_length=len(output)-1, elapsed_ms=int((end - start) * 1000), fname=filen)
    #except:
        # Clean up old files:
        #tmp_dir = op.join(app_dir, "tmp")
        #del_old_files(tmp_dir, days=2)
        #return str(find(inp))
        #return redirect("/")
        #return "Fehler."

@app.route('/download/<filename>', methods=['GET', 'POST'])
def download_file(filename):
    #return f"/home/CPCSE/mysite/static/tmp/{filename}.txt"
    return send_file(f"/home/CPCSE/mysite/static/tmp/{filename}.txt", as_attachment=True)

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/versions")
def versions():
    return render_template("versions.html")

@app.route("/setup")
def setup():
    date_string = time.strftime("%Y-%m-%d")
    session["count"] = [date_string, 0]

    return redirect("/")

@app.route("/error")
def error():
    return render_template("error.html")

@app.route("/download/<fname>")
def download(fname):
    try:
        return send_from_directory("tmp", fname, as_attachment=True)
    except:
        return redirect("/")

@app.route("/reset")
def reset():
    session.clear()

    return redirect("/")

if "__main__" == __name__:
    app.run(debug=True, port=8000)