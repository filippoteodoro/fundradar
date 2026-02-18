fundradar/
  CLAUDE.md

  docs/
    spec.md
    data-model.md
    reliability-contract.md
    ui-notes.md
    context/
      decisions-summary.md
      raw/
        chat-gpt.rtfd

  data/
    pem/ 
	PEM-2000_2001.pdf	 image from page 16
	PEM_2002.pdf	text from page 20 
	PEM_2003.pdf	text from page 20 
	PEM_2004.pdf text from page 20	
	PEM_2005.pdf text from page 22	
	PEM_2006.pdf text from page 24	
	PEM_2007.pdf	text from page 22	
	PEM_2008.pdf	text from page 22		
	PEM_2009.pdf text from page 22	
	PEM_2010.pdf	image from page 22, low quality		
	PEM_2011.pdf	text from page 22		
	PEM_2012.pdf text from page 22
	PEM_2013.pdf	text from page 22
	PEM_2014.pdf text from page 22
	PEM_2015.pdf text from page 22
	PEM_2016.pdf text from page 22
	PEM_2017.pdf text from page 22
	PEM_2018.pdf text from page 22
	PEM_2019.pdf text from page 22
	PEM_2020.pdf text from page 22
	Rapporto-PEM_Ita2021.pdf text from page 20
	PEM_2022-Report.pdf text from page 20
	PEM_2023-Deals.pdf text from page 2
	PEM_2023.pdf
	Rapporto-PEM_2024-1.pdf
	Deals-PEM_2024.pdf text from page 2
		
  apps/
    web/          # Next.js app
    worker/       # Python scraping + parsing jobs

  packages/
    shared/       # shared types + helpers

  scripts/
    seed_pem.ts   # or python equivalent, but keep it deterministic

  .github/
    workflows/
      ci.yml
      cron-worker.yml
