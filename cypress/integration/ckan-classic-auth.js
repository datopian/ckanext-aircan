Cypress.on('uncaught:exception', (err, runnable) => {
  console.log(err);
  return false;
})

describe('Authorized users', () => {
  beforeEach(function(){
    cy.fixture('aircan.json').as('testData').then(() => {
      cy.login(this.testData.username, this.testData.password)
    })
  })

  it('Should Login Successfully', () => {
    cy.get('.username')
  })

  // it('Generate a new API key via UI', () => {
  //   cy.get('.list-unstyled > :nth-child(4) > a').click({force: true})
  //   cy.get('.btn-warning').click()
  //   cy.get('.modal-footer > .btn-primary').click()
  //   cy.contains('Profile updated')
  // })
})
