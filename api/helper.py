import os
import openai

openai.api_key = os.environ.get("OPENAI_API_KEY")


def read_repo_files(repo_path, extensions=[".py"], max_files=10):
    files = []
    for root, _, filenames in os.walk(repo_path):
        for fname in filenames:
            if any(fname.endswith(ext) for ext in extensions):
                full_path = os.path.join(root, fname)
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                files.append((full_path, content))
                if len(files) >= max_files:
                    return files
    return files


def ask_gpt(prompt, files):
    file_texts = "\n\n".join([f"File: {path}\n{content}" for path, content in files])
    full_prompt = f"{prompt}\n\n{file_texts}"

    response = openai.ChatCompletion.create(
        model="gpt-4-turbo",
        messages=[{"role": "user", "content": full_prompt}],
        temperature=0
    )
    return response.choices[0].message.content


if __name__ == "__main__":
    repo_path = "/path/to/your/repo"
    files = read_repo_files(repo_path, max_files=15)
    prompt = "Act as a senior software engineer. Suggest improvements or write a new function to add logging to all API endpoints."
    answer = ask_gpt(prompt, files)
    print(answer)